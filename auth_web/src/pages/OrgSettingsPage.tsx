import { useCallback, useEffect, useState } from "react";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { PageHeader } from "../components/PageHeader";
import { Section } from "../components/Section";
import { Translated, useTranslatedString } from "../components/Translated";
import { useT } from "../context/LocaleContext";
import { useAuthTokens } from "../hooks/useAuthTokens";
import { ApiError, fetchOrgSettings, transferOwnership } from "../lib/api";
import type { OrgSettings } from "../types/app";

export function OrgSettingsPage() {
  const t = useT();
  const selectOwnerLabel = useTranslatedString("Select new owner…");
  const tokens = useAuthTokens();
  const [data, setData] = useState<OrgSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [newOwner, setNewOwner] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!tokens) return;
    try {
      setData(await fetchOrgSettings(tokens));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load organization");
    }
  }, [tokens]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleTransfer = async () => {
    if (!tokens || !newOwner) return;
    setBusy(true);
    setError(null);
    try {
      await transferOwnership(tokens, newOwner);
      setMessage("Ownership transferred.");
      setConfirm(false);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Transfer failed");
    } finally {
      setBusy(false);
    }
  };

  if (!data && !error) {
    return <p className="text-sm text-slate-500">{t("common.loading")}</p>;
  }

  return (
    <div>
      <PageHeader title="Organization" subtitle={data?.name || undefined} />
      {message ? <Alert tone="success">{message}</Alert> : null}
      {error ? (
        <div className="mb-4">
          <Alert tone="error">{error}</Alert>
        </div>
      ) : null}

      {data?.join_code ? (
        <Section title="Join code">
          <p className="text-sm text-slate-600">
            <Translated text="Share with new members:" />
          </p>
          <code className="mt-2 block rounded-lg bg-slate-100 px-4 py-3 font-mono text-lg tracking-widest">
            {data.join_code}
          </code>
        </Section>
      ) : (
        <Alert tone="info">Ask your owner or an approver for the join code.</Alert>
      )}

      {data?.accountants?.length ? (
        <div className="mt-6">
          <Section title="Accountants in your organization">
            <ul className="divide-y divide-gray-100 rounded-lg border border-gray-100">
              {data.accountants.map((a) => (
                <li key={a.user_id} className="flex items-center justify-between px-4 py-3 text-sm">
                  <div>
                    <p className="font-medium text-slate-900">{a.email || a.user_id}</p>
                    {a.job_title ? <p className="text-xs text-slate-500">{a.job_title}</p> : null}
                  </div>
                  {a.is_lead ? (
                    <span className="rounded-full bg-baker-teal/10 px-2 py-0.5 text-xs font-medium text-baker-teal-dark">
                      <Translated text="Lead accountant" />
                    </span>
                  ) : (
                    <span className="text-xs text-slate-400">
                      <Translated text="Accountant" />
                    </span>
                  )}
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-slate-500">
              <Translated text="Owners and admins assign lead accountants from the Members page (approves entries and invoices)." />
            </p>
          </Section>
        </div>
      ) : null}

      {data?.is_owner ? (
        <div className="mt-6">
          <Section title="Transfer ownership">
            <p className="mb-4 text-sm text-slate-600">
              <Translated text="Transfer ownership before deleting your account. The new owner receives full control; you become an admin." />
            </p>
            {!data.transfer_candidates?.length ? (
              <Alert tone="warning">Add another active member before you can transfer ownership.</Alert>
            ) : (
              <>
                <select
                  className="w-full max-w-md rounded-lg border border-gray-200 px-3 py-2 text-sm"
                  value={newOwner}
                  onChange={(e) => setNewOwner(e.target.value)}
                >
                  <option value="">{selectOwnerLabel}</option>
                  {data.transfer_candidates.map((c) => (
                    <option key={c.user_id} value={c.user_id}>
                      {c.email || c.user_id} ({c.org_role})
                    </option>
                  ))}
                </select>
                <label className="mt-3 flex items-center gap-2 text-sm text-slate-600">
                  <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
                  <Translated text="I understand this cannot be undone from this screen." />
                </label>
                <div className="mt-4">
                  <Button type="button" disabled={!confirm || !newOwner || busy} onClick={() => void handleTransfer()}>
                    Transfer ownership
                  </Button>
                </div>
              </>
            )}
          </Section>
        </div>
      ) : (
        <p className="mt-6 text-sm text-slate-500">
          <Translated text="Only the current owner can transfer ownership." />
        </p>
      )}
    </div>
  );
}
