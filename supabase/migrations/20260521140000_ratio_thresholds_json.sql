-- Ratio warning thresholds for accountant home (min/max per KPI).

ALTER TABLE public.app_settings
  ADD COLUMN IF NOT EXISTS ratio_thresholds_json JSONB NOT NULL DEFAULT '{
    "gross_margin_pct": {"min": 25},
    "operating_margin_pct": {"min": 5},
    "quick_ratio": {"min": 1.0}
  }'::jsonb;

COMMENT ON COLUMN public.app_settings.ratio_thresholds_json IS
  'Accountant KPI warning thresholds. Keys: gross_margin_pct, operating_margin_pct, quick_ratio, current_ratio. Each may include min and/or max.';
