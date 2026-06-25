-- Master workbook Google Drive file id (set via admin upload in dashboard; optional override of DRIVE_FILE_ID secret)

ALTER TABLE public.app_settings
  ADD COLUMN IF NOT EXISTS master_workbook_file_id TEXT;

COMMENT ON COLUMN public.app_settings.master_workbook_file_id IS
  'Supabase Storage object path for the master workbook; when set, used instead of MASTER_WORKBOOK_STORAGE_PATH in secrets.';
