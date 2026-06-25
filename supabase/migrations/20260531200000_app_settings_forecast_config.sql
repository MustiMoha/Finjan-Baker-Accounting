-- Lead accountant forecast configuration (methods, drivers, pipeline, weights).
ALTER TABLE public.app_settings
  ADD COLUMN IF NOT EXISTS forecast_config_json JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.app_settings.forecast_config_json IS
  'Revenue/expense forecasting methods, drivers, and scenario parameters.';
