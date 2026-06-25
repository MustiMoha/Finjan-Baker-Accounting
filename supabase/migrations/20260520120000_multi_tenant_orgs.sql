-- Multi-tenant organizations: membership, delegated approvals, org-scoped settings, audit_logs.

-- ---------------------------------------------------------------------------
-- organizations
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL CHECK (char_length(trim(name)) >= 2),
  join_code CHAR(6) NOT NULL UNIQUE,
  owner_user_id UUID NOT NULL REFERENCES auth.users (id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT organizations_join_code_format CHECK (join_code ~ '^[A-Z0-9]{6}$')
);

CREATE INDEX IF NOT EXISTS idx_organizations_owner ON public.organizations (owner_user_id);

-- ---------------------------------------------------------------------------
-- org_members (tenant RBAC)
-- org_role: owner | admin | accountant | user
-- status: pending | active | rejected
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.org_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES public.organizations (id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  org_role TEXT NOT NULL CHECK (org_role IN ('owner', 'admin', 'accountant', 'user')),
  job_title TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'rejected')),
  can_approve BOOLEAN NOT NULL DEFAULT false,
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  reviewed_by UUID REFERENCES auth.users (id),
  reviewed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (org_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_org_members_user ON public.org_members (user_id);
CREATE INDEX IF NOT EXISTS idx_org_members_org_status ON public.org_members (org_id, status);

-- ---------------------------------------------------------------------------
-- audit_logs (central trail)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID REFERENCES public.organizations (id) ON DELETE SET NULL,
  actor_user_id UUID REFERENCES auth.users (id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  target_user_id UUID REFERENCES auth.users (id) ON DELETE SET NULL,
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  success BOOLEAN NOT NULL DEFAULT true,
  client_ip TEXT,
  user_agent TEXT,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_org_time ON public.audit_logs (org_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON public.audit_logs (action, occurred_at DESC);

-- ---------------------------------------------------------------------------
-- Join code generator (36^6 space, uniqueness enforced by retry)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.generate_unique_join_code()
RETURNS CHAR(6)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  chars CONSTANT TEXT := 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  result TEXT := '';
  i INT;
  ch INT;
BEGIN
  LOOP
    result := '';
    FOR i IN 1..6 LOOP
      ch := 1 + floor(random() * 36)::INT;
      result := result || substr(chars, ch, 1);
    END LOOP;
    EXIT WHEN NOT EXISTS (SELECT 1 FROM public.organizations o WHERE o.join_code = result);
  END LOOP;
  RETURN result::CHAR(6);
END;
$$;

GRANT EXECUTE ON FUNCTION public.generate_unique_join_code() TO authenticated;

-- ---------------------------------------------------------------------------
-- Org helpers for RLS
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.org_member_row(p_org_id UUID)
RETURNS public.org_members
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT m.*
  FROM public.org_members m
  WHERE m.org_id = p_org_id
    AND m.user_id = auth.uid()
  LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION public.is_active_org_member(p_org_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.org_members m
    WHERE m.org_id = p_org_id
      AND m.user_id = auth.uid()
      AND m.status = 'active'
  );
$$;

CREATE OR REPLACE FUNCTION public.can_approve_org_members(p_org_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.org_members m
    WHERE m.org_id = p_org_id
      AND m.user_id = auth.uid()
      AND m.status = 'active'
      AND (
        m.org_role = 'owner'
        OR (m.can_approve = true AND m.org_role IN ('owner', 'admin', 'accountant', 'user'))
      )
  );
$$;

CREATE OR REPLACE FUNCTION public.is_org_adminish(p_org_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.org_members m
    WHERE m.org_id = p_org_id
      AND m.user_id = auth.uid()
      AND m.status = 'active'
      AND m.org_role IN ('owner', 'admin')
  );
$$;

GRANT EXECUTE ON FUNCTION public.org_member_row(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_active_org_member(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.can_approve_org_members(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_org_adminish(UUID) TO authenticated;

-- ---------------------------------------------------------------------------
-- app_settings → per-org (migrate singleton row)
-- ---------------------------------------------------------------------------
ALTER TABLE public.app_settings DROP CONSTRAINT IF EXISTS app_settings_id_check;

ALTER TABLE public.app_settings
  ADD COLUMN IF NOT EXISTS org_id UUID UNIQUE REFERENCES public.organizations (id) ON DELETE CASCADE;

DO $$
DECLARE
  default_org_id UUID;
  existing_owner UUID;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.organizations LIMIT 1) THEN
    SELECT ur.user_id INTO existing_owner
    FROM public.user_roles ur
    WHERE ur.role = 'admin'
    ORDER BY ur.created_at
    LIMIT 1;
    IF existing_owner IS NULL THEN
      SELECT id INTO existing_owner FROM auth.users ORDER BY created_at LIMIT 1;
    END IF;
    IF existing_owner IS NOT NULL THEN
      INSERT INTO public.organizations (name, join_code, owner_user_id)
      VALUES ('Default Organization', public.generate_unique_join_code(), existing_owner)
      RETURNING id INTO default_org_id;

      INSERT INTO public.org_members (org_id, user_id, org_role, job_title, status, can_approve)
      SELECT default_org_id, ur.user_id,
        CASE ur.role
          WHEN 'admin' THEN 'admin'
          WHEN 'staff' THEN 'accountant'
          ELSE 'user'
        END,
        '',
        'active',
        (ur.role = 'admin')
      FROM public.user_roles ur
      ON CONFLICT (org_id, user_id) DO NOTHING;

      UPDATE public.organizations
      SET owner_user_id = existing_owner
      WHERE id = default_org_id;

      UPDATE public.org_members
      SET org_role = 'owner', can_approve = true
      WHERE org_id = default_org_id AND user_id = existing_owner;
    END IF;
  END IF;

  SELECT id INTO default_org_id FROM public.organizations ORDER BY created_at LIMIT 1;

  IF default_org_id IS NOT NULL THEN
    UPDATE public.app_settings SET org_id = default_org_id WHERE org_id IS NULL;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- org_id on operational tables
-- ---------------------------------------------------------------------------
ALTER TABLE public.pending_transactions
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations (id) ON DELETE CASCADE;

ALTER TABLE public.account_rules
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations (id) ON DELETE CASCADE;

ALTER TABLE public.gl_lines
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations (id) ON DELETE CASCADE;

ALTER TABLE public.one_time_transaction_marks
  ADD COLUMN IF NOT EXISTS org_id UUID REFERENCES public.organizations (id) ON DELETE CASCADE;

DO $$
DECLARE
  default_org_id UUID;
BEGIN
  SELECT id INTO default_org_id FROM public.organizations ORDER BY created_at LIMIT 1;
  IF default_org_id IS NOT NULL THEN
    UPDATE public.pending_transactions SET org_id = default_org_id WHERE org_id IS NULL;
    UPDATE public.account_rules SET org_id = default_org_id WHERE org_id IS NULL;
    UPDATE public.gl_lines SET org_id = default_org_id WHERE org_id IS NULL;
    UPDATE public.one_time_transaction_marks SET org_id = default_org_id WHERE org_id IS NULL;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Sign-up: defer global role until onboarding (remove auto-staff)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.handle_auth_user_registered()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  -- No automatic user_roles row; onboarding assigns org membership + synced role.
  RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- RLS: organizations, org_members, audit_logs
-- ---------------------------------------------------------------------------
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.org_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS organizations_select_member ON public.organizations;
CREATE POLICY organizations_select_member ON public.organizations
  FOR SELECT TO authenticated
  USING (
    public.is_active_org_member(id)
    OR EXISTS (
      SELECT 1 FROM public.org_members m
      WHERE m.org_id = organizations.id AND m.user_id = auth.uid()
    )
  );

DROP POLICY IF EXISTS organizations_insert_authenticated ON public.organizations;
CREATE POLICY organizations_insert_authenticated ON public.organizations
  FOR INSERT TO authenticated
  WITH CHECK (owner_user_id = auth.uid());

DROP POLICY IF EXISTS organizations_update_owner ON public.organizations;
CREATE POLICY organizations_update_owner ON public.organizations
  FOR UPDATE TO authenticated
  USING (owner_user_id = auth.uid())
  WITH CHECK (owner_user_id = auth.uid());

DROP POLICY IF EXISTS org_members_select ON public.org_members;
CREATE POLICY org_members_select ON public.org_members
  FOR SELECT TO authenticated
  USING (
    user_id = auth.uid()
    OR public.is_org_adminish(org_id)
    OR public.can_approve_org_members(org_id)
  );

DROP POLICY IF EXISTS org_members_insert_self ON public.org_members;
CREATE POLICY org_members_insert_self ON public.org_members
  FOR INSERT TO authenticated
  WITH CHECK (
    user_id = auth.uid()
    AND status = 'pending'
    AND org_role = 'user'
    AND can_approve = false
  );

DROP POLICY IF EXISTS org_members_insert_owner ON public.org_members;
CREATE POLICY org_members_insert_owner ON public.org_members
  FOR INSERT TO authenticated
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.organizations o
      WHERE o.id = org_id AND o.owner_user_id = auth.uid()
    )
    AND user_id = auth.uid()
    AND org_role = 'owner'
    AND status = 'active'
    AND can_approve = true
  );

DROP POLICY IF EXISTS org_members_update_admin ON public.org_members;
CREATE POLICY org_members_update_admin ON public.org_members
  FOR UPDATE TO authenticated
  USING (public.is_org_adminish(org_id) OR public.can_approve_org_members(org_id))
  WITH CHECK (public.is_org_adminish(org_id) OR public.can_approve_org_members(org_id));

DROP POLICY IF EXISTS audit_logs_select_org ON public.audit_logs;
CREATE POLICY audit_logs_select_org ON public.audit_logs
  FOR SELECT TO authenticated
  USING (
    org_id IS NULL
    OR public.is_org_adminish(org_id)
    OR public.can_approve_org_members(org_id)
  );

DROP POLICY IF EXISTS audit_logs_insert ON public.audit_logs;
CREATE POLICY audit_logs_insert ON public.audit_logs
  FOR INSERT TO authenticated
  WITH CHECK (actor_user_id = auth.uid() OR actor_user_id IS NULL);

GRANT SELECT, INSERT, UPDATE ON public.organizations TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.org_members TO authenticated;
GRANT SELECT, INSERT ON public.audit_logs TO authenticated;

-- Extend app_settings select/update to active org members
DROP POLICY IF EXISTS app_settings_select ON public.app_settings;
CREATE POLICY app_settings_select ON public.app_settings
  FOR SELECT TO authenticated
  USING (
    org_id IS NULL
    OR public.is_active_org_member(org_id)
  );

DROP POLICY IF EXISTS app_settings_update_admin ON public.app_settings;
CREATE POLICY app_settings_update_admin ON public.app_settings
  FOR UPDATE TO authenticated
  USING (
    (org_id IS NOT NULL AND public.is_active_org_member(org_id) AND public.is_org_adminish(org_id))
    OR (org_id IS NULL AND public.has_role(ARRAY['admin']))
  )
  WITH CHECK (
    (org_id IS NOT NULL AND public.is_active_org_member(org_id) AND public.is_org_adminish(org_id))
    OR (org_id IS NULL AND public.has_role(ARRAY['admin']))
  );

DROP POLICY IF EXISTS app_settings_insert_org ON public.app_settings;
CREATE POLICY app_settings_insert_org ON public.app_settings
  FOR INSERT TO authenticated
  WITH CHECK (
    org_id IS NOT NULL AND public.is_active_org_member(org_id)
  );
