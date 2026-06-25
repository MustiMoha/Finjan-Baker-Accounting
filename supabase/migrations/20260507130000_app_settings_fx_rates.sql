-- Manual FX multipliers: row amount * rate[currency] = amount in display_currency_iso
-- Example: display USD, EUR rate 1.09 → 100 EUR * 1.09 = 109 USD

ALTER TABLE public.app_settings
  ADD COLUMN IF NOT EXISTS fx_rates_json JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.app_settings.fx_rates_json IS
  'Map of ISO 4217 code (uppercase) to numeric multiplier into display_currency_iso (amount_display = amount_row * rate). Omit or use 1 for display currency.';
