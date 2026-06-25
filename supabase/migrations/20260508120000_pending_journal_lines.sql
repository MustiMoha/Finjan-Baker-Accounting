-- Compound journal entries: multiple debit/credit lines per pending row.
-- When journal_lines is set, amount and single debit/credit account columns are NULL.

ALTER TABLE public.pending_transactions
  ADD COLUMN IF NOT EXISTS journal_lines JSONB;

ALTER TABLE public.pending_transactions
  DROP CONSTRAINT IF EXISTS pending_transactions_amount_check;

ALTER TABLE public.pending_transactions
  ADD CONSTRAINT pending_transactions_amount_pos CHECK (amount IS NULL OR amount > 0);

ALTER TABLE public.pending_transactions
  ALTER COLUMN amount DROP NOT NULL,
  ALTER COLUMN debit_account DROP NOT NULL,
  ALTER COLUMN credit_account DROP NOT NULL;

ALTER TABLE public.pending_transactions
  DROP CONSTRAINT IF EXISTS pending_transactions_entry_mode;

ALTER TABLE public.pending_transactions
  ADD CONSTRAINT pending_transactions_entry_mode CHECK (
    (
      journal_lines IS NULL
      AND amount IS NOT NULL
      AND debit_account IS NOT NULL
      AND btrim(debit_account) <> ''
      AND credit_account IS NOT NULL
      AND btrim(credit_account) <> ''
    )
    OR (
      journal_lines IS NOT NULL
      AND jsonb_typeof(journal_lines) = 'array'
      AND jsonb_array_length(journal_lines) >= 2
      AND amount IS NULL
      AND debit_account IS NULL
      AND credit_account IS NULL
    )
  );

COMMENT ON COLUMN public.pending_transactions.journal_lines IS
  'Balanced compound entry: JSON array of {account, debit, credit} as strings; exactly one of debit/credit positive per line.';
