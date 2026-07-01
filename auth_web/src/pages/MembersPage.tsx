import { useCallback, useEffect, useState } from "react";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { PageHeader } from "../components/PageHeader";
import { Section } from "../components/Section";
import { Translated } from "../components/Translated";
import { useAuthTokens } from "../hooks/useAuthTokens";
import { ApiError, fetchMembers, updateMember } from "../lib/api";
import type { OrgMember } from "../types/app";
import { TablePageSkeleton } from "../components/Skeleton";

export function MembersPage() {
  const tokens = useAuthTokens();
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, { org_role: string; can_approve: boolean }>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);

  const load = useCallback(async () => {
    if (!tokens) return;
    try {
      const rows = await fetchMembers(tokens);
      const active = rows.filter((m) => m.status === "active");
      setMembers(active);
      const d: Record<string, { org_role: string; can_approve: boolean }> = {};
      for (const m of active) {
        d[m.id] = { org_role: m.org_role, can_approve: Boolean(m.can_approve) };
      }
      setDrafts(d);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load members");
    } finally {
      setInitialLoading(false);
    }
  }, [tokens]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (memberId: string) => {
    if (!tokens) return;
    const d = drafts[memberId];
    if (!d) return;
    setBusyId(memberId);
    try {
      await updateMember(tokens, memberId, {
        org_role: d.org_role as "admin" | "accountant" | "user",
        can_approve: d.can_approve,
      });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Update failed");
    } finally {
      setBusyId(null);
    }
  };

  if (initialLoading) {
    return <TablePageSkeleton />;
  }

  return (
    <div>
      <PageHeader
        title="Members"
        subtitle="Manage roles. For accountants, enable Lead accountant to approve entries, invoices, and join requests."
      />
      {error ? <Alert tone="error">{error}</Alert> : null}

      <div className="space-y-3">
        {members.map((m) => {
          const email = m.profiles?.email || m.user_id;
          const isOwner = m.org_role === "owner";
          const d = drafts[m.id];
          return (
            <Section key={m.id}>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="font-medium text-slate-900">{email}</p>
                  <p className="text-xs text-slate-500">{m.job_title || "—"}</p>
                </div>
                {isOwner ? (
                  <p className="text-sm text-slate-500">
                    <Translated text="Owner — transfer via Organization settings." />
                  </p>
                ) : d ? (
                  <div className="flex flex-wrap items-end gap-3">
                    <label className="text-sm">
                      <span className="mb-1 block text-xs text-slate-500">
                        <Translated text="Role" />
                      </span>
                      <select
                        className="rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
                        value={d.org_role}
                        onChange={(e) =>
                          setDrafts({ ...drafts, [m.id]: { ...d, org_role: e.target.value } })
                        }
                      >
                        <option value="admin">admin</option>
                        <option value="accountant">accountant</option>
                        <option value="user">user</option>
                      </select>
                    </label>
                    {d.org_role === "accountant" ? (
                      <label className="flex max-w-xs flex-col gap-1 text-sm text-slate-600">
                        <span className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={d.can_approve}
                            onChange={(e) =>
                              setDrafts({ ...drafts, [m.id]: { ...d, can_approve: e.target.checked } })
                            }
                          />
                          <Translated text="Lead accountant" />
                        </span>
                        <span className="text-xs text-slate-500">
                          <Translated text="Can approve journal entries, invoices, and member join requests." />
                        </span>
                      </label>
                    ) : null}
                    <Button type="button" disabled={busyId === m.id} onClick={() => void save(m.id)}>
                      Save
                    </Button>
                  </div>
                ) : null}
              </div>
            </Section>
          );
        })}
      </div>
    </div>
  );
}
