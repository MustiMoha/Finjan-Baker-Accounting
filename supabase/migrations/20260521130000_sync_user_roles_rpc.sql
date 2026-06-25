-- Sync user_roles from org membership (SECURITY DEFINER bypasses admin-only INSERT RLS).

CREATE OR REPLACE FUNCTION public.org_role_to_legacy_role(p_org_role TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE lower(trim(COALESCE(p_org_role, '')))
    WHEN 'owner' THEN 'admin'
    WHEN 'admin' THEN 'admin'
    WHEN 'accountant' THEN 'staff'
    ELSE 'auditor'
  END;
$$;

CREATE OR REPLACE FUNCTION public.sync_legacy_user_role_from_org(p_org_role TEXT)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_uid UUID := auth.uid();
  v_legacy TEXT;
BEGIN
  IF v_uid IS NULL THEN
    RAISE EXCEPTION 'Not authenticated';
  END IF;

  v_legacy := public.org_role_to_legacy_role(p_org_role);

  INSERT INTO public.user_roles (user_id, role)
  VALUES (v_uid, v_legacy)
  ON CONFLICT (user_id) DO UPDATE
    SET role = EXCLUDED.role;
END;
$$;

-- Replace create org RPC to sync legacy role in the same transaction.
CREATE OR REPLACE FUNCTION public.create_organization_with_owner(
  p_name TEXT,
  p_job_title TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_uid UUID := auth.uid();
  v_code CHAR(6);
  v_org public.organizations;
  v_name TEXT := trim(p_name);
  v_title TEXT := trim(p_job_title);
  v_settings_id SMALLINT;
BEGIN
  IF v_uid IS NULL THEN
    RAISE EXCEPTION 'Not authenticated';
  END IF;

  IF char_length(v_name) < 2 THEN
    RAISE EXCEPTION 'Organization name must be at least 2 characters.';
  END IF;

  IF v_title = '' THEN
    RAISE EXCEPTION 'Enter your role title (e.g. CFO, Controller).';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.org_members m
    WHERE m.user_id = v_uid
      AND m.status IN ('active', 'pending')
  ) THEN
    RAISE EXCEPTION 'You already belong to an organization or have a pending request.';
  END IF;

  v_code := public.generate_unique_join_code();

  INSERT INTO public.organizations (name, join_code, owner_user_id)
  VALUES (v_name, v_code, v_uid)
  RETURNING * INTO v_org;

  INSERT INTO public.org_members (
    org_id, user_id, org_role, job_title, status, can_approve
  )
  VALUES (v_org.id, v_uid, 'owner', v_title, 'active', true);

  SELECT COALESCE(MAX(id), 0) + 1 INTO v_settings_id FROM public.app_settings;

  INSERT INTO public.app_settings (id, org_id, fiscal_year_start_month, updated_by)
  VALUES (v_settings_id, v_org.id, 1, v_uid);

  INSERT INTO public.user_roles (user_id, role)
  VALUES (v_uid, 'admin')
  ON CONFLICT (user_id) DO UPDATE
    SET role = EXCLUDED.role;

  RETURN to_jsonb(v_org);
END;
$$;

GRANT EXECUTE ON FUNCTION public.org_role_to_legacy_role(TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.sync_legacy_user_role_from_org(TEXT) TO authenticated;
