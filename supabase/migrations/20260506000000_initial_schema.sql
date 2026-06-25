-- Accounting dashboard: core tables, enums, RLS
-- Apply via Supabase SQL Editor or CLI: supabase db push

-- Roles reference (application level; stored as text)
-- Valid values: 'admin', 'staff', 'auditor'

CREATE TABLE IF NOT EXISTS public.user_roles (
  user_id UUID PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('admin', 'staff', 'auditor')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.app_settings (
  id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  fiscal_year_start_month SMALLINT NOT NULL DEFAULT 1 CHECK (fiscal_year_start_month BETWEEN 1 AND 12),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_by UUID REFERENCES auth.users (id)
);

INSERT INTO public.app_settings (id, fiscal_year_start_month)
VALUES (1, 1)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.account_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  keyword TEXT NOT NULL,
  debit_account TEXT NOT NULL,
  credit_account TEXT NOT NULL,
  priority INT NOT NULL DEFAULT 0,
  active BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_account_rules_active_keyword ON public.account_rules (active, keyword);

CREATE TABLE IF NOT EXISTS public.pending_transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_by UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  description TEXT NOT NULL,
  amount NUMERIC(18, 2) NOT NULL CHECK (amount > 0),
  debit_account TEXT NOT NULL,
  credit_account TEXT NOT NULL,
  posting_date DATE NOT NULL DEFAULT (CURRENT_DATE),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
  reviewed_by UUID REFERENCES auth.users (id),
  reviewed_at TIMESTAMPTZ,
  drive_revision_id TEXT,
  last_error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pending_status ON public.pending_transactions (status);
CREATE INDEX IF NOT EXISTS idx_pending_created_by ON public.pending_transactions (created_by);

CREATE TABLE IF NOT EXISTS public.gl_lines (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pending_transaction_id UUID REFERENCES public.pending_transactions (id) ON DELETE SET NULL,
  gl_date DATE NOT NULL,
  description TEXT NOT NULL,
  account TEXT NOT NULL,
  debit NUMERIC(18, 2) NOT NULL DEFAULT 0 CHECK (debit >= 0),
  credit NUMERIC(18, 2) NOT NULL DEFAULT 0 CHECK (credit >= 0),
  fiscal_year INT NOT NULL,
  fiscal_period INT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT gl_lines_one_side_positive CHECK (
    (debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0)
  )
);

CREATE INDEX IF NOT EXISTS idx_gl_lines_fiscal ON public.gl_lines (fiscal_year, fiscal_period);
CREATE INDEX IF NOT EXISTS idx_gl_lines_date ON public.gl_lines (gl_date);

-- RLS
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.account_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pending_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gl_lines ENABLE ROW LEVEL SECURITY;

-- Helper: current user has one of these roles
CREATE OR REPLACE FUNCTION public.has_role(p_roles TEXT[])
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.user_roles ur
    WHERE ur.user_id = auth.uid()
      AND ur.role = ANY (p_roles)
  );
$$;

GRANT EXECUTE ON FUNCTION public.has_role(TEXT[]) TO authenticated;

-- user_roles: read own row only (admin provisioning via dashboard / service role)
DROP POLICY IF EXISTS user_roles_select_own ON public.user_roles;
CREATE POLICY user_roles_select_own ON public.user_roles
  FOR SELECT TO authenticated
  USING (user_id = auth.uid());

-- app_settings: anyone authenticated can read; only admin updates
DROP POLICY IF EXISTS app_settings_select ON public.app_settings;
CREATE POLICY app_settings_select ON public.app_settings
  FOR SELECT TO authenticated
  USING (true);

DROP POLICY IF EXISTS app_settings_update_admin ON public.app_settings;
CREATE POLICY app_settings_update_admin ON public.app_settings
  FOR UPDATE TO authenticated
  USING (public.has_role(ARRAY['admin']))
  WITH CHECK (public.has_role(ARRAY['admin']));

-- account_rules: admin full write; staff/auditor read
DROP POLICY IF EXISTS account_rules_select ON public.account_rules;
CREATE POLICY account_rules_select ON public.account_rules
  FOR SELECT TO authenticated
  USING (
    public.has_role(ARRAY['admin', 'staff', 'auditor'])
  );

DROP POLICY IF EXISTS account_rules_admin_write ON public.account_rules;
CREATE POLICY account_rules_admin_write ON public.account_rules
  FOR ALL TO authenticated
  USING (public.has_role(ARRAY['admin']))
  WITH CHECK (public.has_role(ARRAY['admin']));

-- pending_transactions
DROP POLICY IF EXISTS pending_select ON public.pending_transactions;
CREATE POLICY pending_select ON public.pending_transactions
  FOR SELECT TO authenticated
  USING (
    created_by = auth.uid()
    OR public.has_role(ARRAY['admin', 'auditor'])
  );

DROP POLICY IF EXISTS pending_insert ON public.pending_transactions;
CREATE POLICY pending_insert ON public.pending_transactions
  FOR INSERT TO authenticated
  WITH CHECK (
    created_by = auth.uid()
    AND public.has_role(ARRAY['staff', 'admin'])
  );

DROP POLICY IF EXISTS pending_update_staff_own ON public.pending_transactions;
CREATE POLICY pending_update_staff_own ON public.pending_transactions
  FOR UPDATE TO authenticated
  USING (
    created_by = auth.uid()
    AND public.has_role(ARRAY['staff', 'admin'])
    AND status = 'pending'
  )
  WITH CHECK (
    created_by = auth.uid()
    AND status = 'pending'
  );

DROP POLICY IF EXISTS pending_update_admin ON public.pending_transactions;
CREATE POLICY pending_update_admin ON public.pending_transactions
  FOR UPDATE TO authenticated
  USING (public.has_role(ARRAY['admin']))
  WITH CHECK (public.has_role(ARRAY['admin']));

-- gl_lines
DROP POLICY IF EXISTS gl_lines_select ON public.gl_lines;
CREATE POLICY gl_lines_select ON public.gl_lines
  FOR SELECT TO authenticated
  USING (
    public.has_role(ARRAY['admin', 'staff', 'auditor'])
  );

DROP POLICY IF EXISTS gl_lines_insert_admin ON public.gl_lines;
CREATE POLICY gl_lines_insert_admin ON public.gl_lines
  FOR INSERT TO authenticated
  WITH CHECK (public.has_role(ARRAY['admin']));

-- Seed sample rules (optional; skip if rows already exist)
INSERT INTO public.account_rules (keyword, debit_account, credit_account, priority, active)
SELECT * FROM (VALUES
  ('office supplies', '6100-expense', '2000-ap', 10, true),
  ('utilities', '6200-utilities', '2000-ap', 10, true),
  ('payroll', '6500-payroll', '2100-payable', 10, true)
) AS v(keyword, debit_account, credit_account, priority, active)
WHERE NOT EXISTS (SELECT 1 FROM public.account_rules LIMIT 1);
