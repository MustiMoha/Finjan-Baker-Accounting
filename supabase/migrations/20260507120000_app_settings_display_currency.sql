-- ISO 4217 code for labeling amounts on dashboard / journal (no FX conversion baked in)



ALTER TABLE public.app_settings

  ADD COLUMN IF NOT EXISTS display_currency_iso TEXT NOT NULL DEFAULT 'USD';



COMMENT ON COLUMN public.app_settings.display_currency_iso IS

  'Presentation currency symbol for amounts (USD, EUR, ...). Rows may still carry their own inferred currency_iso from the sheet.';


