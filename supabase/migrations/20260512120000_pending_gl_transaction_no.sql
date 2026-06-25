-- Optional override for the workbook «Tr. No.» / transaction column when posting approved entries.
-- NULL means infer the next number from the ledger tail at post time (existing behavior).

ALTER TABLE public.pending_transactions
  ADD COLUMN IF NOT EXISTS gl_transaction_no TEXT;

COMMENT ON COLUMN public.pending_transactions.gl_transaction_no IS
  'When set, written to the GL transaction number column on approve; when NULL, next number is inferred from the workbook.';
