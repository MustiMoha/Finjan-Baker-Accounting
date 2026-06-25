-- Admin-tagged GL rows (workbook-derived fingerprints) for “one-time” / non-recurring buckets.

CREATE TABLE IF NOT EXISTS public.one_time_transaction_marks (
  fingerprint TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by UUID REFERENCES auth.users (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_one_time_marks_created_at ON public.one_time_transaction_marks (created_at DESC);

ALTER TABLE public.one_time_transaction_marks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS one_time_marks_select ON public.one_time_transaction_marks;
CREATE POLICY one_time_marks_select ON public.one_time_transaction_marks
  FOR SELECT TO authenticated
  USING (public.has_role(ARRAY['admin', 'staff', 'auditor']::TEXT[]));

DROP POLICY IF EXISTS one_time_marks_insert_admin ON public.one_time_transaction_marks;
CREATE POLICY one_time_marks_insert_admin ON public.one_time_transaction_marks
  FOR INSERT TO authenticated
  WITH CHECK (public.has_role(ARRAY['admin']::TEXT[]));

DROP POLICY IF EXISTS one_time_marks_update_admin ON public.one_time_transaction_marks;
CREATE POLICY one_time_marks_update_admin ON public.one_time_transaction_marks
  FOR UPDATE TO authenticated
  USING (public.has_role(ARRAY['admin']::TEXT[]))
  WITH CHECK (public.has_role(ARRAY['admin']::TEXT[]));

DROP POLICY IF EXISTS one_time_marks_delete_admin ON public.one_time_transaction_marks;
CREATE POLICY one_time_marks_delete_admin ON public.one_time_transaction_marks
  FOR DELETE TO authenticated
  USING (public.has_role(ARRAY['admin']::TEXT[]));

GRANT SELECT ON public.one_time_transaction_marks TO authenticated;
GRANT INSERT, UPDATE, DELETE ON public.one_time_transaction_marks TO authenticated;

COMMENT ON TABLE public.one_time_transaction_marks IS
  'Fingerprints of journal entries marked one-time by admins (see gl_transaction_fingerprint; compound entries share one id).';
