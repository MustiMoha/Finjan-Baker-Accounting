import { useCallback, useEffect, useState } from "react";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { Label } from "../components/Label";
import { PageHeader } from "../components/PageHeader";
import { Section } from "../components/Section";
import { Translated, useTranslatedString } from "../components/Translated";
import { useAuthTokens } from "../hooks/useAuthTokens";
import { ApiError, fetchAccountantBuckets, patchAccountantBuckets } from "../lib/api";
import { foldBucketKey, pickLongerDisplayName } from "../lib/foldBucketKey";
import type { AccountBucket, AccountBucketMapping, AccountBucketsDoc } from "../types/app";

const NEW_BUCKET = "__new__";
const CATEGORIES = ["asset", "liability", "equity", "revenue", "expense"] as const;

type BucketRow = AccountBucket & { _remove?: boolean };
type RuleRow = AccountBucketMapping & { bucket_name: string; _remove?: boolean };
type RuleRowExt = RuleRow & { _newName?: string; _newCategory?: string };

function emptyBucket(name = "New bucket", category = "asset"): BucketRow {
  return {
    id: crypto.randomUUID(),
    name,
    category,
    template_key: "",
    rollup: true,
    heuristic: false,
  };
}

function findBucketIdByName(buckets: BucketRow[], name: string): string | undefined {
  const key = foldBucketKey(name);
  return buckets.find((b) => !b._remove && foldBucketKey(b.name) === key)?.id;
}

function mergeBucketsCaseInsensitive(rows: BucketRow[]): BucketRow[] {
  const order: string[] = [];
  const byKey = new Map<string, BucketRow>();
  for (const row of rows) {
    if (row._remove || !row.name.trim()) {
      continue;
    }
    const key = foldBucketKey(row.name);
    const prev = byKey.get(key);
    if (!prev) {
      byKey.set(key, { ...row });
      order.push(key);
      continue;
    }
    prev.name = pickLongerDisplayName(prev.name, row.name);
    prev.heuristic = Boolean(prev.heuristic) || Boolean(row.heuristic);
    prev.rollup = Boolean(prev.rollup) || Boolean(row.rollup);
    if (!prev.template_key && row.template_key) {
      prev.template_key = row.template_key;
    }
  }
  return order.map((k) => byKey.get(k)!);
}

export function AccountClassificationPage() {
  const tokens = useAuthTokens();
  const containsPh = useTranslatedString("e.g. payroll, rent, visa");
  const newBucketPh = useTranslatedString("New bucket name");
  const bucketNamePh = useTranslatedString("Bucket name");
  const anyTextOpt = useTranslatedString("Any transaction text");
  const accountOnlyOpt = useTranslatedString("Account name only");
  const newBucketOpt = useTranslatedString("+ New bucket…");
  const [buckets, setBuckets] = useState<BucketRow[]>([]);
  const [rules, setRules] = useState<RuleRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!tokens) return;
    try {
      const doc = await fetchAccountantBuckets(tokens);
      const b = mergeBucketsCaseInsensitive((doc.buckets || []).map((x) => ({ ...x })));
      const nameById = Object.fromEntries(b.map((x) => [x.id, x.name]));
      const r: RuleRow[] = (doc.mappings || []).map((m) => ({
        ...m,
        bucket_name: nameById[m.bucket_id] || "",
        field: (m.field === "account" ? "account" : "any") as "account" | "any",
      }));
      setBuckets(b.length ? b : [emptyBucket()]);
      setRules(r);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load classification rules");
    }
  }, [tokens]);

  useEffect(() => {
    void load();
  }, [load]);

  const activeBuckets = buckets.filter((b) => !b._remove && b.name.trim());
  const bucketNames = activeBuckets.map((b) => b.name);

  const resolvePendingBuckets = (): { buckets: BucketRow[]; rules: RuleRow[] } => {
    let nextBuckets = [...buckets];
    const nextRules = rules.map((row) => {
      if (row._remove || row.bucket_name !== NEW_BUCKET) {
        return row;
      }
      const ext = row as RuleRowExt;
      const nm = (ext._newName || row.text).trim();
      if (!nm) {
        return row;
      }
      if (!findBucketIdByName(nextBuckets, nm)) {
        nextBuckets = [...nextBuckets, emptyBucket(nm, ext._newCategory || "asset")];
      }
      const id = findBucketIdByName(nextBuckets, nm)!;
      return { ...row, bucket_name: nm, bucket_id: id };
    });
    return { buckets: nextBuckets, rules: nextRules };
  };

  const buildDocFrom = (resolvedBuckets: BucketRow[], resolvedRules: RuleRow[]): AccountBucketsDoc => {
    const kept = resolvedBuckets.filter((b) => !b._remove && b.name.trim());
    const nameToId = Object.fromEntries(kept.map((b) => [foldBucketKey(b.name), b.id]));
    const maps: AccountBucketMapping[] = [];
    for (const row of resolvedRules) {
      if (row._remove || !row.text.trim()) continue;
      const bucketName = row.bucket_name.trim();
      if (!bucketName || bucketName === NEW_BUCKET) continue;
      const bid = nameToId[foldBucketKey(bucketName)] || row.bucket_id;
      if (!bid) continue;
      maps.push({
        bucket_id: bid,
        text: row.text.trim(),
        match: row.match === "equals" ? "equals" : "contains",
        field: row.field === "account" ? "account" : "any",
      });
    }
    return {
      buckets: kept.map(({ _remove, ...b }) => ({
        ...b,
        name: b.name.trim(),
        category: b.category || "asset",
        template_key: b.template_key || "",
      })),
      mappings: maps,
    };
  };

  const buildDoc = (): AccountBucketsDoc => {
    const pending = resolvePendingBuckets();
    return buildDocFrom(pending.buckets, pending.rules);
  };

  const save = async () => {
    if (!tokens) return;
    const pending = resolvePendingBuckets();
    const incomplete = pending.rules.some(
      (row) => !row._remove && row.bucket_name === NEW_BUCKET && !(row as RuleRowExt)._newName?.trim() && !row.text.trim(),
    );
    if (incomplete) {
      setError("Finish creating a bucket for each new-bucket rule, or choose an existing bucket.");
      return;
    }
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      await patchAccountantBuckets(tokens, buildDoc());
      setMessage("Classification saved — recorded in the audit log.");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const addRuleRow = () => {
    setRules([
      ...rules,
      {
        bucket_id: activeBuckets[0]?.id || "",
        bucket_name: bucketNames[0] || "",
        text: "",
        match: "contains",
        field: "any",
      },
    ]);
  };

  const updateRuleBucket = (index: number, value: string) => {
    setRules(
      rules.map((r, j) => {
        if (j !== index) return r;
        if (value === NEW_BUCKET) {
          return { ...r, bucket_name: NEW_BUCKET, bucket_id: "" };
        }
        const id = findBucketIdByName(buckets, value);
        return { ...r, bucket_name: value, bucket_id: id || r.bucket_id };
      }),
    );
  };

  const commitNewBucketFromRule = (index: number, name: string, category: string) => {
    const nm = name.trim();
    if (!nm) return;
    let nextBuckets = buckets;
    if (!findBucketIdByName(buckets, nm)) {
      nextBuckets = [...buckets, emptyBucket(nm, category)];
      setBuckets(nextBuckets);
    }
    const id = findBucketIdByName(nextBuckets, nm)!;
    setRules(
      rules.map((r, j) =>
        j === index ? { ...r, bucket_name: nm, bucket_id: id, _newName: undefined } : r,
      ),
    );
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="Account classification"
        subtitle="Map ledger lines to buckets using words in the account name or anywhere on the transaction."
      />
      {message ? <Alert tone="success">{message}</Alert> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}

      <Section title="Match rules">
        <p className="mb-3 text-sm text-slate-600">
          <Translated text="Map ledger lines to buckets using a word or phrase. Choose Any text to match in the account, description, details, or particulars; choose Account to match the account name only. Rules are checked in order (longer phrases first). First match wins. Pick an existing bucket or create a new one inline." />
        </p>
        <div className="space-y-3">
          {rules.map((r, i) => {
            if (r._remove) return null;
            const ext = r as RuleRowExt;
            const creating = r.bucket_name === NEW_BUCKET;
            return (
              <div
                key={`rule-${i}-${r.text}-${r.bucket_id}`}
                className="rounded-lg border border-gray-100 bg-white p-3 shadow-sm"
              >
                <div className="grid gap-2 md:grid-cols-12 md:items-end">
                  <label className="md:col-span-3 text-xs">
                    <Label text="Contains" className="text-slate-500" />
                    <input
                      className="mt-0.5 w-full rounded border border-gray-200 px-2 py-1.5 text-sm"
                      placeholder={containsPh}
                      value={r.text}
                      onChange={(e) =>
                        setRules(rules.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))
                      }
                    />
                  </label>
                  <label className="md:col-span-2 text-xs">
                    <Label text="In" className="text-slate-500" />
                    <select
                      className="mt-0.5 w-full rounded border border-gray-200 px-2 py-1.5 text-sm"
                      value={r.field === "account" ? "account" : "any"}
                      onChange={(e) =>
                        setRules(
                          rules.map((x, j) =>
                            j === i ? { ...x, field: e.target.value as "account" | "any" } : x,
                          ),
                        )
                      }
                    >
                      <option value="any">{anyTextOpt}</option>
                      <option value="account">{accountOnlyOpt}</option>
                    </select>
                  </label>
                  <label className="md:col-span-4 text-xs">
                    <Label text="Bucket" className="text-slate-500" />
                    <select
                      className="mt-0.5 w-full rounded border border-gray-200 px-2 py-1.5 text-sm"
                      value={creating ? NEW_BUCKET : r.bucket_name}
                      onChange={(e) => updateRuleBucket(i, e.target.value)}
                    >
                      <option value="">…</option>
                      {bucketNames.map((n) => (
                        <option key={n} value={n}>
                          {n}
                        </option>
                      ))}
                      <option value={NEW_BUCKET}>{newBucketOpt}</option>
                    </select>
                  </label>
                  <button
                    type="button"
                    className="md:col-span-3 text-sm text-rose-600"
                    onClick={() => setRules(rules.map((x, j) => (j === i ? { ...x, _remove: true } : x)))}
                  >
                    Remove rule
                  </button>
                </div>
                {creating ? (
                  <div className="mt-3 grid gap-2 border-t border-gray-100 pt-3 sm:grid-cols-3">
                    <input
                      className="rounded border border-gray-200 px-2 py-1.5 text-sm sm:col-span-2"
                      placeholder={r.text.trim() || newBucketPh}
                      value={ext._newName ?? ""}
                      onChange={(e) =>
                        setRules(
                          rules.map((x, j) =>
                            j === i ? { ...x, _newName: e.target.value } : x,
                          ),
                        )
                      }
                    />
                    <select
                      className="rounded border border-gray-200 px-2 py-1.5 text-sm"
                      value={ext._newCategory ?? "asset"}
                      onChange={(e) =>
                        setRules(
                          rules.map((x, j) =>
                            j === i ? { ...x, _newCategory: e.target.value } : x,
                          ),
                        )
                      }
                    >
                      {CATEGORIES.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                    <Button
                      type="button"
                      variant="secondary"
                      className="!w-auto sm:col-span-3"
                      onClick={() =>
                        commitNewBucketFromRule(
                          i,
                          ext._newName || r.text,
                          ext._newCategory || "asset",
                        )
                      }
                    >
                      Create bucket for this rule
                    </Button>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
        {rules.filter((r) => !r._remove).length === 0 ? (
          <p className="text-sm text-slate-500">
            <Translated text="No match rules yet. Add one below." />
          </p>
        ) : null}
        <Button type="button" variant="secondary" className="mt-3 !w-auto" onClick={addRuleRow}>
          Add rule
        </Button>
      </Section>

      <Section title="Buckets">
        <p className="mb-3 text-sm text-slate-600">
          <Translated text="Each bucket has a financial category (asset, liability, equity, revenue, expense). Balance-sheet ratios use asset, liability, and equity." />
        </p>
        <div className="space-y-3">
          {buckets.map((b, i) =>
            b._remove ? null : (
              <div key={b.id} className="grid gap-2 rounded-lg border border-gray-100 bg-slate-50/50 p-3 md:grid-cols-12">
                <input
                  className="md:col-span-4 rounded border border-gray-200 px-2 py-1.5 text-sm"
                  placeholder={bucketNamePh}
                  value={b.name}
                  onChange={(e) =>
                    setBuckets(buckets.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))
                  }
                />
                <select
                  className="md:col-span-3 rounded border border-gray-200 px-2 py-1.5 text-sm"
                  value={b.category}
                  onChange={(e) =>
                    setBuckets(buckets.map((x, j) => (j === i ? { ...x, category: e.target.value } : x)))
                  }
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
                <label className="md:col-span-2 flex items-center gap-1 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={Boolean(b.rollup)}
                    onChange={(e) =>
                      setBuckets(buckets.map((x, j) => (j === i ? { ...x, rollup: e.target.checked } : x)))
                    }
                  />
                  Roll up
                </label>
                <button
                  type="button"
                  className="md:col-span-3 text-left text-sm text-rose-600"
                  onClick={() => setBuckets(buckets.map((x, j) => (j === i ? { ...x, _remove: true } : x)))}
                >
                  Remove bucket
                </button>
              </div>
            ),
          )}
        </div>
        <Button
          type="button"
          variant="secondary"
          className="mt-3 !w-auto"
          onClick={() => setBuckets([...buckets, emptyBucket()])}
        >
          + Bucket
        </Button>
      </Section>

      <Button type="button" disabled={busy} onClick={() => void save()}>
        Save classification
      </Button>
    </div>
  );
}
