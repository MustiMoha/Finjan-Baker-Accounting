-- GL / T-Accounts worksheet names for master workbook (no longer hard-coded to "GL")



ALTER TABLE public.app_settings

  ADD COLUMN IF NOT EXISTS master_workbook_gl_sheet_name TEXT,

  ADD COLUMN IF NOT EXISTS master_workbook_t_accounts_sheet_name TEXT;



COMMENT ON COLUMN public.app_settings.master_workbook_gl_sheet_name IS

  'Worksheet name used for posting and GL preview (e.g. General Ledger); default GL if unset.';



COMMENT ON COLUMN public.app_settings.master_workbook_t_accounts_sheet_name IS

  'Worksheet reserved for T-accounts layout (reference for admins; optional).';


