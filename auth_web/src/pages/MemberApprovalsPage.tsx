import { useCallback, useEffect, useState } from "react";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { PageHeader } from "../components/PageHeader";
import { Section } from "../components/Section";
import { Translated } from "../components/Translated";
import { useAuthTokens } from "../hooks/useAuthTokens";
import { ApiError, approveMember, fetchPendingMembers, rejectMember } from "../lib/api";
import type { OrgMember } from "../types/app";
import { TablePageSkeleton } from "../components/Skeleton";

export function MemberApprovalsPage() {
  const tokens = useAuthTokens();
  const [pending, setPending] = useState<OrgMember[]>([]);
  const [roles, setRoles] = useState<Record<string, "user" | "accountant" | "admin">>({});
  const [leadFlags, setLeadFlags] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);

  const load = useCallback(async () => {
    if (!tokens) return;
    try {
      const rows = await fetchPendingMembers(tokens);
      setPending(rows);
      const r: Record<string, "user" | "accountant" | "admin"> = {};
      const l: Record<string, boolean> = {};
      for (const m of rows) {
        r[m.id] = "user";
        l[m.id] = false;
      }
      setRoles(r);
      setLeadFlags(l);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load pending members");
    } finally {
      setInitialLoading(false);
    }
  }, [tokens]);

  useEffect(() => {
    void load();
  }, [load]);

  if (initialLoading) {
    return <TablePageSkeleton />;
  }

  return (
    <div>
      <PageHeader title="Member approvals" subtitle="Approve or reject join requests." />
      {error ? <Alert tone="error">{error}</Alert> : null}

      {!pending.length ? (
        <Alert tone="info">No pending join requests.</Alert>
      ) : (
        <div className="space-y-4">
          <Alert tone="warning">
            {pending.length} <Translated text="member(s) waiting for approval." />
          </Alert>
          {pending.map((m) => {
            const email = m.profiles?.email || m.user_id;
            const role = roles[m.id] || "user";
            return (
              <Section key={m.id}>
                <p className="font-medium text-slate-900">{email}</p>
                <p className="text-sm text-slate-500">{m.job_title || "—"}</p>
                <div className="mt-3 flex flex-wrap items-end gap-3">
                  <label className="text-sm">
                    <span className="mb-1 block text-xs text-slate-500">
                      <Translated text="Role on approval" />
                    </span>
                    <select
                      className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
                      value={role}
                      onChange={(e) =>
                        setRoles({
                          ...roles,
                          [m.id]: e.target.value as "user" | "accountant" | "admin",
                        })
                      }
                    >
                      <option value="user">user</option>
                      <option value="accountant">accountant</option>
                      <option value="admin">admin</option>
                    </select>
                  </label>
                  {role === "accountant" ? (
                    <label className="flex items-center gap-2 text-sm text-slate-600">
                      <input
                        type="checkbox"
                        checked={leadFlags[m.id] ?? false}
                        onChange={(e) => setLeadFlags({ ...leadFlags, [m.id]: e.target.checked })}
                      />
                      <Translated text="Lead accountant" />
                    </label>
                  ) : null}
                  <Button
                    type="button"
                    disabled={busyId === m.id}
                    onClick={async () => {
                      if (!tokens) return;
                      setBusyId(m.id);
                      try {
                        await approveMember(tokens, m.id, role, leadFlags[m.id] ?? false);
                        await load();
                      } catch (err) {
                        setError(err instanceof ApiError ? err.message : "Approve failed");
                      } finally {
                        setBusyId(null);
                      }
                    }}
                  >
                    Approve
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={busyId === m.id}
                    onClick={async () => {
                      if (!tokens) return;
                      setBusyId(m.id);
                      try {
                        await rejectMember(tokens, m.id);
                        await load();
                      } catch (err) {
                        setError(err instanceof ApiError ? err.message : "Reject failed");
                      } finally {
                        setBusyId(null);
                      }
                    }}
                  >
                    Reject
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
