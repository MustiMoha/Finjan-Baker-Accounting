import { useCallback, useEffect, useState } from "react";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { DataTable } from "../components/DataTable";
import { FileInput } from "../components/FileInput";
import { InputField } from "../components/InputField";
import { JournalLinesTable } from "../components/JournalLinesTable";
import { Label } from "../components/Label";
import { Modal } from "../components/Modal";
import { PageHeader } from "../components/PageHeader";
import { Section } from "../components/Section";
import { Translated, useTranslatedString } from "../components/Translated";
import { useAppContext } from "../context/AppContext";
import { useAuthTokens } from "../hooks/useAuthTokens";
import {
  ApiError,
  createPendingEntry,
  extractInvoice,
  fetchMyPending,
} from "../lib/api";
import type { InvoiceExtractResult, PendingTransaction } from "../types/app";

type JournalLine = { account: string; debit: string; credit: string };

const EMPTY_LINE = (): JournalLine => ({ account: "", debit: "", credit: "" });

export function EntriesPage() {
  const tokens = useAuthTokens();
  const { ctx } = useAppContext();
  const displayCurrency = ctx?.display_currency || "USD";
  const accountPh = useTranslatedString("Account");
  const debitPh = useTranslatedString("Debit");
  const creditPh = useTranslatedString("Credit");
  const [description, setDescription] = useState("");
  const [postingDate, setPostingDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [currency, setCurrency] = useState(displayCurrency);
  const [glTr, setGlTr] = useState("");
  const [lines, setLines] = useState<JournalLine[]>([EMPTY_LINE(), EMPTY_LINE()]);
  const [invoiceDraft, setInvoiceDraft] = useState<InvoiceExtractResult | null>(null);
  const [recent, setRecent] = useState<PendingTransaction[]>([]);
  const [selected, setSelected] = useState<PendingTransaction | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setCurrency(displayCurrency);
  }, [displayCurrency]);

  const loadRecent = useCallback(async () => {
    if (!tokens) return;
    try {
      const rows = await fetchMyPending(tokens);
      setRecent(rows.filter((r) => r.status === "pending"));
    } catch {
      /* ignore */
    }
  }, [tokens]);

  useEffect(() => {
    void loadRecent();
    const id = window.setInterval(() => void loadRecent(), 10000);
    return () => window.clearInterval(id);
  }, [loadRecent]);

  const updateLine = (idx: number, field: keyof JournalLine, value: string) => {
    setLines((prev) => prev.map((ln, i) => (i === idx ? { ...ln, [field]: value } : ln)));
  };

  const handleExtract = async (file: File) => {
    if (!tokens) return;
    setError(null);
    setBusy(true);
    try {
      const res = await extractInvoice(tokens, file);
      setInvoiceDraft(res);
      setDescription(res.draft.description || "");
      if (res.draft.posting_date) setPostingDate(res.draft.posting_date);
      if (res.draft.currency_iso) setCurrency(res.draft.currency_iso);
      else setCurrency(displayCurrency);
      const jl = res.draft.journal_lines.length >= 2 ? res.draft.journal_lines : [EMPTY_LINE(), EMPTY_LINE()];
      setLines(jl);
      setMessage(
        res.draft.usable_amounts
          ? "Filled from invoice — review amounts and accounts."
          : "Limited data from file — enter amounts manually if needed.",
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Extract failed");
    } finally {
      setBusy(false);
    }
  };

  const handleSubmit = async () => {
    if (!tokens) return;
    setError(null);
    setMessage(null);
    setBusy(true);
    try {
      const filled = lines.filter((ln) => ln.account.trim() || ln.debit.trim() || ln.credit.trim());
      if (filled.length < 2) throw new Error("Add at least two journal lines.");
      await createPendingEntry(tokens, {
        description,
        posting_date: postingDate,
        currency_iso: currency,
        journal_lines: filled,
        gl_transaction_no: glTr.trim() || undefined,
        invoice_extraction_json: invoiceDraft?.extraction,
        invoice_base64: invoiceDraft?.invoice_base64,
        invoice_filename: invoiceDraft?.invoice_filename,
      });
      setDescription("");
      setGlTr("");
      setLines([EMPTY_LINE(), EMPTY_LINE()]);
      setInvoiceDraft(null);
      setCurrency(displayCurrency);
      setMessage("Sent for approval.");
      await loadRecent();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Submit failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Entries & invoices"
        subtitle="Submit journal entries for admin approval. Attach an invoice to pre-fill amounts."
      />

      {message ? <Alert tone="success">{message}</Alert> : null}
      {error ? (
        <div className="mt-3">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      <Section title="Start from an invoice">
        <div className="max-w-lg">
          <FileInput
            accept=".pdf,.png,.jpg,.jpeg,.webp"
            disabled={busy}
            label="Choose invoice file"
            hint="PDF or image — amounts and accounts may be pre-filled."
            selectedName={invoiceDraft?.invoice_filename}
            onFile={(f) => void handleExtract(f)}
          />
        </div>
      </Section>

      <div className="mt-6 space-y-4">
        <Section>
          <div className="grid gap-4 md:grid-cols-2">
            <InputField label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
            <InputField
              label="Posting date"
              type="date"
              value={postingDate}
              onChange={(e) => setPostingDate(e.target.value)}
            />
            <InputField
              label={`Currency (presentation: ${displayCurrency})`}
              value={currency}
              onChange={(e) => setCurrency(e.target.value.toUpperCase())}
            />
            <InputField
              label="GL transaction # (optional)"
              value={glTr}
              onChange={(e) => setGlTr(e.target.value)}
            />
          </div>

          <div className="mt-6">
            <p className="mb-2 text-sm font-medium text-slate-700">
              <Translated text="Journal lines" />
            </p>
            <div className="space-y-2">
              {lines.map((ln, i) => (
                <div key={i} className="grid grid-cols-12 gap-2">
                  <input
                    className="col-span-5 rounded-lg border border-gray-200 px-3 py-2 text-sm"
                    placeholder={accountPh}
                    value={ln.account}
                    onChange={(e) => updateLine(i, "account", e.target.value)}
                  />
                  <input
                    className="col-span-3 rounded-lg border border-gray-200 px-3 py-2 text-sm"
                    placeholder={debitPh}
                    value={ln.debit}
                    onChange={(e) => updateLine(i, "debit", e.target.value)}
                  />
                  <input
                    className="col-span-3 rounded-lg border border-gray-200 px-3 py-2 text-sm"
                    placeholder={creditPh}
                    value={ln.credit}
                    onChange={(e) => updateLine(i, "credit", e.target.value)}
                  />
                  <button
                    type="button"
                    className="col-span-1 text-slate-400 hover:text-rose-600"
                    onClick={() => lines.length > 2 && setLines(lines.filter((_, j) => j !== i))}
                    disabled={lines.length <= 2}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
            <div className="mt-3 flex gap-2">
              <Button type="button" variant="secondary" onClick={() => setLines([...lines, EMPTY_LINE()])} disabled={lines.length >= 16}>
                + Line
              </Button>
            </div>
          </div>

          <div className="mt-6">
            <Button type="button" onClick={() => void handleSubmit()} disabled={busy}>
              Submit for approval
            </Button>
          </div>
        </Section>

        <Section title="My recent requests">
          <p className="mb-3 text-sm text-slate-600">
            <Translated text="Click a row to view the full entry." />
          </p>
          <DataTable
            rows={recent as unknown as Record<string, unknown>[]}
            columns={[
              { key: "description", label: "Description" },
              { key: "currency_iso", label: "Currency" },
              { key: "posting_date", label: "Posting date" },
              {
                key: "created_at",
                label: "Submitted",
                render: (row) => {
                  const v = row.created_at as string | undefined;
                  return v ? new Date(v).toLocaleString() : "—";
                },
              },
            ]}
            emptyMessage="Nothing waiting right now."
            onRowClick={(row) => setSelected(row as unknown as PendingTransaction)}
          />
        </Section>
      </div>

      <Modal
        title={selected?.description || "Transaction"}
        open={selected != null}
        onClose={() => setSelected(null)}
      >
        {selected ? (
          <div className="space-y-4 text-sm text-slate-700">
            <dl className="grid gap-2 md:grid-cols-2">
              <div>
                <Label text="Status:" className="text-slate-500" /> {selected.status}
              </div>
              <div>
                <Label text="Currency:" className="text-slate-500" /> {selected.currency_iso || "—"}
              </div>
              <div>
                <Label text="Posting date:" className="text-slate-500" /> {selected.posting_date}
              </div>
              <div>
                <Label text="Submitted:" className="text-slate-500" />{" "}
                {selected.created_at ? new Date(selected.created_at).toLocaleString() : "—"}
              </div>
              {selected.gl_transaction_no ? (
                <div>
                  <Label text="GL #:" className="text-slate-500" /> {selected.gl_transaction_no}
                </div>
              ) : null}
            </dl>
            {selected.journal_lines && selected.journal_lines.length >= 2 ? (
              <JournalLinesTable lines={selected.journal_lines} />
            ) : (
              <dl className="grid gap-2 md:grid-cols-2">
                <div>
                  <Label text="Amount:" /> {selected.amount ?? "—"}
                </div>
                <div>
                  <Label text="Debit:" /> {selected.debit_account ?? "—"}
                </div>
                <div>
                  <Label text="Credit:" /> {selected.credit_account ?? "—"}
                </div>
              </dl>
            )}
            {selected.invoice_url ? (
              <a href={selected.invoice_url} className="text-baker-teal-dark underline" target="_blank" rel="noreferrer">
                {selected.invoice_original_filename || <Translated text="View invoice" />}
              </a>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
