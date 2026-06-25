-- Private Supabase Storage bucket for the master workbook; RLS aligns with dashboard roles.



INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)

VALUES (

  'accounting-master',

  'accounting-master',

  false,

  52428800,

  ARRAY[

    'application/vnd.ms-excel',

    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',

    'application/vnd.ms-excel.sheet.macroEnabled.12',

    'text/csv'

  ]::TEXT[]

)

ON CONFLICT (id) DO NOTHING;



DROP POLICY IF EXISTS accounting_master_select_authenticated ON storage.objects;

CREATE POLICY accounting_master_select_authenticated

  ON storage.objects FOR SELECT TO authenticated

  USING (bucket_id = 'accounting-master');



DROP POLICY IF EXISTS accounting_master_insert_admin ON storage.objects;

CREATE POLICY accounting_master_insert_admin

  ON storage.objects FOR INSERT TO authenticated

  WITH CHECK (

    bucket_id = 'accounting-master'

    AND public.has_role(ARRAY['admin']::TEXT[])

  );



DROP POLICY IF EXISTS accounting_master_update_admin ON storage.objects;

CREATE POLICY accounting_master_update_admin

  ON storage.objects FOR UPDATE TO authenticated

  USING (

    bucket_id = 'accounting-master'

    AND public.has_role(ARRAY['admin']::TEXT[])

  )

  WITH CHECK (

    bucket_id = 'accounting-master'

    AND public.has_role(ARRAY['admin']::TEXT[])

  );



DROP POLICY IF EXISTS accounting_master_delete_admin ON storage.objects;

CREATE POLICY accounting_master_delete_admin

  ON storage.objects FOR DELETE TO authenticated

  USING (

    bucket_id = 'accounting-master'

    AND public.has_role(ARRAY['admin']::TEXT[])

  );



COMMENT ON COLUMN public.app_settings.master_workbook_file_id IS

  'Supabase Storage object path within MASTER_WORKBOOK_BUCKET (no leading slash), e.g. master/workbook.xlsm. Optional override of MASTER_WORKBOOK_STORAGE_PATH in secrets.';

