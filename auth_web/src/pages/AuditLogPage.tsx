import { useCallback, useEffect, useState } from "react";
import { Alert } from "../components/Alert";
import { DataTable } from "../components/DataTable";
import { PageHeader } from "../components/PageHeader";
import { Section } from "../components/Section";
import { Translated } from "../components/Translated";
import { useAuthTokens } from "../hooks/useAuthTokens";
import { ApiError, fetchOrgAudit, fetchSignInAudit } from "../lib/api";

export function AuditLogPage() {
  const tokens = useAuthTokens();
  const [tab, setTab] = useState<"org" | "signin">("org");
  const [orgRows, setOrgRows] = useState<Record<string, unknown>[]>([]);
  const [signInRows, setSignInRows] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!tokens) return;
    try {
      const [org, signin] = await Promise.all([fetchOrgAudit(tokens), fetchSignInAudit(tokens)]);
      setOrgRows(org);
      setSignInRows(signin);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load audit log");
    }
  }, [tokens]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div>
      <PageHeader title="Audit log" />
      {error ? <Alert tone="error">{error}</Alert> : null}

      <div className="mb-4 flex gap-2">
        <button
          type="button"
          className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
            tab === "org" ? "bg-baker-teal/10 text-baker-teal-dark" : "text-slate-600 hover:bg-slate-100"
          }`}
          onClick={() => setTab("org")}
        >
          <Translated text="Organization events" />
        </button>
        <button
          type="button"
          className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
            tab === "signin" ? "bg-baker-teal/10 text-baker-teal-dark" : "text-slate-600 hover:bg-slate-100"
          }`}
          onClick={() => setTab("signin")}
        >
          <Translated text="Sign-in history" />
        </button>
      </div>

      <Section>
        {tab === "org" ? (
          <DataTable
            rows={orgRows}
            columns={[
              { key: "occurred_at", label: "When" },
              {
                key: "summary",
                label: "Event",
                render: (row) => String(row.summary || row.action || "—"),
              },
              {
                key: "actor_email",
                label: "User email",
                render: (row) => String(row.actor_email || "—"),
              },
              { key: "action", label: "Action code" },
              { key: "success", label: "OK" },
            ]}
            emptyMessage="No organization events logged yet."
          />
        ) : (
          <DataTable
            rows={signInRows}
            columns={[
              { key: "occurred_at", label: "When" },
              { key: "email", label: "Email" },
              { key: "role", label: "Role" },
              { key: "client_ip", label: "IP" },
            ]}
            emptyMessage="Nothing logged yet."
          />
        )}
      </Section>
    </div>
  );
}
