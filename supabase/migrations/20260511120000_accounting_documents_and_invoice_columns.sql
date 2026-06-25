-- Private bucket for invoice uploads and statement templates (PDF/images/spreadsheets).

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'accounting-documents',
  'accounting-documents',
  false,
  52428800,
  ARRAY[
    'application/pdf',
    'image/png',
    'image/jpeg',
    'image/webp',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'application/vnd.ms-excel.sheet.macroEnabled.12',
    'application/vnd.ms-excel',
    'text/csv'
  ]::TEXT[]
)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS accounting_documents_select ON storage.objects;
CREATE POLICY accounting_documents_select
  ON storage.objects FOR SELECT TO authenticated
  USING (bucket_id = 'accounting-documents');

DROP POLICY IF EXISTS accounting_documents_insert_invoices ON storage.objects;
CREATE POLICY accounting_documents_insert_invoices
  ON storage.objects FOR INSERT TO authenticated
  WITH CHECK (
    bucket_id = 'accounting-documents'
    AND public.has_role(ARRAY['staff', 'admin']::TEXT[])
    AND split_part(name, '/', 1) = 'invoices'
  );

DROP POLICY IF EXISTS accounting_documents_insert_templates ON storage.objects;
CREATE POLICY accounting_documents_insert_templates
  ON storage.objects FOR INSERT TO authenticated
  WITH CHECK (
    bucket_id = 'accounting-documents'
    AND public.has_role(ARRAY['admin']::TEXT[])
    AND split_part(name, '/', 1) = 'templates'
  );

DROP POLICY IF EXISTS accounting_documents_update_invoices ON storage.objects;
CREATE POLICY accounting_documents_update_invoices
  ON storage.objects FOR UPDATE TO authenticated
  USING (
    bucket_id = 'accounting-documents'
    AND split_part(name, '/', 1) = 'invoices'
    AND public.has_role(ARRAY['staff', 'admin']::TEXT[])
  )
  WITH CHECK (
    bucket_id = 'accounting-documents'
    AND split_part(name, '/', 1) = 'invoices'
    AND public.has_role(ARRAY['staff', 'admin']::TEXT[])
  );

DROP POLICY IF EXISTS accounting_documents_update_templates ON storage.objects;
CREATE POLICY accounting_documents_update_templates
  ON storage.objects FOR UPDATE TO authenticated
  USING (
    bucket_id = 'accounting-documents'
    AND split_part(name, '/', 1) = 'templates'
    AND public.has_role(ARRAY['admin']::TEXT[])
  )
  WITH CHECK (
    bucket_id = 'accounting-documents'
    AND split_part(name, '/', 1) = 'templates'
    AND public.has_role(ARRAY['admin']::TEXT[])
  );

DROP POLICY IF EXISTS accounting_documents_delete_admin ON storage.objects;
CREATE POLICY accounting_documents_delete_admin
  ON storage.objects FOR DELETE TO authenticated
  USING (
    bucket_id = 'accounting-documents'
    AND public.has_role(ARRAY['admin']::TEXT[])
  );

ALTER TABLE public.pending_transactions
  ADD COLUMN IF NOT EXISTS invoice_object_path TEXT,
  ADD COLUMN IF NOT EXISTS invoice_original_filename TEXT,
  ADD COLUMN IF NOT EXISTS invoice_extraction_json JSONB;

COMMENT ON COLUMN public.pending_transactions.invoice_object_path IS
  'Supabase Storage path in accounting-documents bucket, e.g. invoices/{pending_id}/file.pdf';
COMMENT ON COLUMN public.pending_transactions.invoice_extraction_json IS
  'Normalized extract from invoice (vendor, dates, totals, line_items, warnings).';

ALTER TABLE public.app_settings
  ADD COLUMN IF NOT EXISTS statement_templates_json JSONB NOT NULL DEFAULT '{}'::JSONB;

COMMENT ON COLUMN public.app_settings.statement_templates_json IS
  'Per-kind template paths in accounting-documents, e.g. {"trial_balance":{"object_path":"templates/statements/tb.xlsx","updated_at":"..."}}.';
