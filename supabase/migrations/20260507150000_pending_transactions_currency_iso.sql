-- Optional ISO 4217 for queued staff entries (drives Excel number format on post).

ALTER TABLE public.pending_transactions
  ADD COLUMN IF NOT EXISTS currency_iso TEXT NOT NULL DEFAULT 'USD';
