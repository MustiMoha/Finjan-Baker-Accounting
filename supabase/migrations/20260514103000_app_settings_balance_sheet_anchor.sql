-- Optional workbook anchors for Financials statements (cross-check balances against master file).

ALTER TABLE public.app_settings
  ADD COLUMN IF NOT EXISTS balance_sheet_anchor_json JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.app_settings.balance_sheet_anchor_json IS
  '{"retained_earnings":{"sheet":"Balance Sheet","cell_a1":"B20"}} sheet + A1-style cell pointing at workbook Retained earnings.';
