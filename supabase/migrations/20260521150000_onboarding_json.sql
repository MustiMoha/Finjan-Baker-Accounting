-- Org onboarding wizard state (role pick + workbook upload).

ALTER TABLE public.app_settings
  ADD COLUMN IF NOT EXISTS onboarding_json JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.app_settings.onboarding_json IS
  'Org setup wizard: setup_completed, chosen_view_role, workbook_skipped, completed_at.';
