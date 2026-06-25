import { Label } from "../components/Label";
import { Translated } from "../components/Translated";
import { useCallback, useEffect, useState } from "react";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { JournalLinesTable } from "../components/JournalLinesTable";
import { PageHeader } from "../components/PageHeader";
import { Section } from "../components/Section";
import { useAppContext } from "../context/AppContext";
import { useAuthTokens } from "../hooks/useAuthTokens";
import { ApiError, approvePending, fetchPendingQueue, rejectPending } from "../lib/api";
import type { PendingTransaction } from "../types/app";

const POLL_MS = 5000;

export function ApprovalsPage() {
  const tokens = useAuthTokens();
  const { reload: reloadCtx } = useAppContext();
  const [rows, setRows] = useState<PendingTransaction[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!tokens) return;
    try {
      setRows(await fetchPendingQueue(tokens));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load queue");
    }
  }, [tokens]);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const act = async (id: string, action: "approve" | "reject") => {
    if (!tokens) return;
    setBusyId(id);
    try {
      if (action === "approve") await approvePending(tokens, id);
      else await rejectPending(tokens, id);
      await load();
      await reloadCtx();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Action failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <PageHeader title="Entry approvals" subtitle="Review and post pending journal entries to the workbook." />
      {error ? <Alert tone="error">{error}</Alert> : null}

      {!rows.length ? (
        <Alert tone="info">No transactions waiting.</Alert>
      ) : (
        <div className="space-y-4">
          {rows.map((r) => {
            const jl = r.journal_lines;
            const multi = jl && jl.length >= 2;
            return (
              <Section key={r.id} title={(r.description || "Entry").slice(0, 72)}>
                <dl className="mb-3 grid gap-1 text-sm text-slate-700 md:grid-cols-2">
                  <div className="md:col-span-2">
                    <Label text="Submitted by:" className="text-slate-500" />{" "}
                    {r.submitter_name || r.submitter_email || <Translated text="Unknown user" />}
                    {r.submitter_name && r.submitter_email ? (
                      <span className="text-slate-500"> ({r.submitter_email})</span>
                    ) : null}
                  </div>
                  <div>
                    <Label text="Status:" className="text-slate-500" /> {r.status}
                  </div>
                  <div>
                    <Label text="Currency:" className="text-slate-500" /> {r.currency_iso || "—"}
                  </div>
                  <div>
                    <Label text="Posting date:" className="text-slate-500" /> {r.posting_date}
                  </div>
                  <div>
                    <Label text="Submitted:" className="text-slate-500" />{" "}
                    {r.created_at ? new Date(r.created_at).toLocaleString() : "—"}
                  </div>
                  {r.gl_transaction_no ? (
                    <div>
                      <Label text="GL #:" className="text-slate-500" /> {r.gl_transaction_no}
                    </div>
                  ) : null}
                </dl>
                {multi ? (
                  <JournalLinesTable lines={jl} />
                ) : (
                  <dl className="grid gap-1 text-sm text-slate-700 md:grid-cols-2">
                    <div>
                      <Label text="Amount:" /> {r.amount ?? "—"}
                    </div>
                    <div>
                      <Label text="Debit:" /> {r.debit_account ?? "—"}
                    </div>
                    <div>
                      <Label text="Credit:" /> {r.credit_account ?? "—"}
                    </div>
                  </dl>
                )}
                {r.invoice_url ? (
                  <p className="mt-2 text-sm">
                    <a href={r.invoice_url} className="text-baker-teal-dark underline" target="_blank" rel="noreferrer">
                      {r.invoice_original_filename || <Translated text="Download invoice" />}
                    </a>
                  </p>
                ) : null}
                {r.last_error ? <Alert tone="error">{r.last_error}</Alert> : null}
                <div className="mt-4 flex gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={busyId === r.id}
                    onClick={() => void act(r.id, "reject")}
                  >
                    Reject
                  </Button>
                  <Button type="button" disabled={busyId === r.id} onClick={() => void act(r.id, "approve")}>
                    Approve & post
                  </Button>
                </div>
              </Section>
            );
          })}
        </div>
      )}
    </div>
  );
}
