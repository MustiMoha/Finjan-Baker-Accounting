import { useCallback, useEffect, useState } from "react";
import { Alert } from "../components/Alert";
import { useReloadOnWindowFocus } from "../hooks/useReloadOnWindowFocus";
import { Button } from "../components/Button";
import { Modal } from "../components/Modal";
import { PageHeader } from "../components/PageHeader";
import { Section } from "../components/Section";
import { Translated } from "../components/Translated";
import { useLocale } from "../context/LocaleContext";
import { useAuthTokens } from "../hooks/useAuthTokens";
import { useEffectivePermissions } from "../hooks/useEffectivePermissions";
import { ApiError, fetchAccountantHome, patchAccountantThresholds } from "../lib/api";
import type { AccountantHomePayload, AccountantRatio } from "../types/app";
import { AccountantHomePageSkeleton } from "../components/Skeleton";

const THRESHOLD_KEYS = [
  "current_ratio",
  "net_profit_margin",
  "return_on_equity",
  "debt_to_equity",
  "interest_coverage",
] as const;

const RATIO_CATEGORIES: { id: string; title: string; keys: readonly string[] }[] = [
  { id: "liquidity", title: "Liquidity", keys: ["current_ratio", "quick_ratio"] },
  { id: "profitability", title: "Profitability", keys: ["net_profit_margin", "return_on_equity"] },
  { id: "efficiency", title: "Efficiency", keys: ["asset_turnover"] },
  { id: "solvency", title: "Solvency", keys: ["debt_to_equity", "interest_coverage"] },
];

const RATIO_LABELS: Record<string, string> = {
  current_ratio: "Current ratio",
  net_profit_margin: "Net profit margin",
  return_on_equity: "Return on equity",
  debt_to_equity: "Debt to equity",
  interest_coverage: "Interest coverage",
  quick_ratio: "Quick ratio",
  asset_turnover: "Asset turnover",
};

function formatRatioValue(ratio: AccountantRatio): string {
  if (ratio.value == null) return "N/A";
  return `${ratio.value}${ratio.unit === "%" ? "%" : ""}`;
}

function RatioCard({
  ratioKey,
  ratio,
  onSelect,
}: {
  ratioKey: string;
  ratio: AccountantRatio;
  onSelect: () => void;
}) {
  const { locale, translateText, prefetchTexts } = useLocale();
  const label = RATIO_LABELS[ratioKey] || ratioKey.replace(/_/g, " ");

  useEffect(() => {
    if (locale === "ar") {
      prefetchTexts([label, ratio.caption, "View breakdown →"].filter(Boolean));
    }
  }, [locale, label, ratio.caption, prefetchTexts]);

  return (
    <button
      type="button"
      className="rounded-lg border border-gray-100 bg-slate-50/50 p-4 text-left transition hover:border-baker-teal/40 hover:bg-baker-teal/5 focus:outline-none focus:ring-2 focus:ring-baker-teal/30"
      onClick={onSelect}
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {translateText(label)}
      </p>
      <p className="mt-2 text-3xl font-semibold text-slate-900">{formatRatioValue(ratio)}</p>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">{translateText(ratio.caption)}</p>
      <p className="mt-2 text-xs font-medium text-baker-teal-dark">
        <Translated text="View breakdown →" />
      </p>
    </button>
  );
}

export function AccountantHomePage() {
  const { locale, translateText, prefetchTexts } = useLocale();
  const tokens = useAuthTokens();
  const { permissions } = useEffectivePermissions();
  const [data, setData] = useState<AccountantHomePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, { min: string; max: string }>>({});
  const [busy, setBusy] = useState(false);
  const [ratioModal, setRatioModal] = useState<{ key: string; ratio: AccountantRatio } | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);

  const load = useCallback(async () => {
    if (!tokens) return;
    try {
      const res = await fetchAccountantHome(tokens);
      setData(res);
      const d: Record<string, { min: string; max: string }> = {};
      for (const k of THRESHOLD_KEYS) {
        const t = res.thresholds[k];
        d[k] = {
          min: t?.min != null ? String(t.min) : "",
          max: t?.max != null ? String(t.max) : "",
        };
      }
      setDraft(d);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load accountant home");
    } finally {
      setInitialLoading(false);
    }
  }, [tokens]);

  useEffect(() => {
    void load();
  }, [load]);

  useReloadOnWindowFocus(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const saveThresholds = async () => {
    if (!tokens) return;
    setBusy(true);
    setMessage(null);
    try {
      const thresholds: Record<string, { min?: number; max?: number }> = {};
      for (const k of THRESHOLD_KEYS) {
        const row = draft[k];
        if (!row) continue;
        const entry: { min?: number; max?: number } = {};
        if (row.min.trim()) entry.min = Number(row.min);
        if (row.max.trim()) entry.max = Number(row.max);
        thresholds[k] = entry;
      }
      await patchAccountantThresholds(tokens, thresholds);
      setMessage("Thresholds saved — change recorded in audit log.");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const leadBadge = permissions?.is_lead_accountant ? (
    <span className="ml-2 rounded-full bg-baker-teal/10 px-2 py-0.5 text-xs font-medium text-baker-teal-dark">
      <Translated text="Lead accountant" />
    </span>
  ) : null;

  const subtitle = permissions?.is_lead_accountant
    ? "Monitor ratios, set warning thresholds, and approve entries or members when assigned as lead."
    : "Monitor ratios and set warning thresholds. Post entries from the menu; approvals require lead accountant.";

  useEffect(() => {
    if (locale !== "ar" || !data) return;
    const texts = [
      subtitle,
      "Click a ratio to see how it was calculated.",
      "Set minimum or maximum values. When a ratio crosses a threshold, a warning appears above. Changes are written to the audit log.",
      "All monitored ratios are within your thresholds.",
      "No breakdown available — upload a workbook with GL activity.",
      ...RATIO_CATEGORIES.map((c) => c.title),
      ...Object.values(RATIO_LABELS),
      ...data.warnings.map((w) => w.message),
    ];
    prefetchTexts(texts);
  }, [locale, data, subtitle, prefetchTexts]);

  if (initialLoading && !data && !error) {
    return <AccountantHomePageSkeleton />;
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title={
          <>
            <Translated text="Accountant home" />
            {leadBadge}
          </>
        }
        subtitle={subtitle}
      />

      {message ? <Alert tone="success">{message}</Alert> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}

      {data?.warnings.length ? (
        <div className="space-y-2">
          {data.warnings.map((w) => (
            <Alert key={w.metric} tone="warning">
              {w.message}
            </Alert>
          ))}
        </div>
      ) : data ? (
        <Alert tone="info">All monitored ratios are within your thresholds.</Alert>
      ) : null}

      {data ? (
        <>
          <Section title="Key financial ratios">
            <p className="mb-6 text-sm text-slate-600">
              <Translated text="Click a ratio to see how it was calculated." />
            </p>
            <div className="space-y-8">
              {RATIO_CATEGORIES.map((category) => {
                const items = category.keys
                  .map((key) => ({ key, ratio: data.ratios[key] }))
                  .filter((item): item is { key: string; ratio: AccountantRatio } => item.ratio != null);
                if (!items.length) return null;
                return (
                  <div key={category.id}>
                    <h3 className="mb-3 border-b border-gray-100 pb-2 text-sm font-semibold text-slate-800">
                      <Translated text={category.title} />
                    </h3>
                    <div className="grid gap-4 md:grid-cols-2">
                      {items.map(({ key, ratio }) => (
                        <RatioCard
                          key={key}
                          ratioKey={key}
                          ratio={ratio}
                          onSelect={() => setRatioModal({ key, ratio })}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </Section>

          <Section title="Warning thresholds">
            <p className="mb-4 text-sm text-slate-600">
              <Translated text="Set minimum or maximum values. When a ratio crosses a threshold, a warning appears above. Changes are written to the audit log." />
            </p>
            <div className="space-y-6">
              {RATIO_CATEGORIES.map((category) => {
                const keys = category.keys.filter((k) =>
                  (THRESHOLD_KEYS as readonly string[]).includes(k),
                );
                if (!keys.length) return null;
                return (
                  <div key={category.id}>
                    <h3 className="mb-2 text-sm font-semibold text-slate-800">
                      <Translated text={category.title} />
                    </h3>
                    <div className="space-y-3">
                      {keys.map((key) => (
                        <div key={key} className="grid grid-cols-12 items-center gap-2 text-sm">
                          <span className="col-span-4 font-medium text-slate-700">
                            {translateText(RATIO_LABELS[key] || key.replace(/_/g, " "))}
                          </span>
                          <label className="col-span-3">
                            <span className="text-xs text-slate-500">
                              <Translated text="Min" />
                            </span>
                            <input
                              className="mt-0.5 w-full rounded border border-gray-200 px-2 py-1.5"
                              value={draft[key]?.min ?? ""}
                              onChange={(e) =>
                                setDraft({
                                  ...draft,
                                  [key]: { ...draft[key], min: e.target.value, max: draft[key]?.max ?? "" },
                                })
                              }
                            />
                          </label>
                          <label className="col-span-3">
                            <span className="text-xs text-slate-500">
                              <Translated text="Max" />
                            </span>
                            <input
                              className="mt-0.5 w-full rounded border border-gray-200 px-2 py-1.5"
                              value={draft[key]?.max ?? ""}
                              onChange={(e) =>
                                setDraft({ ...draft, [key]: { min: draft[key]?.min ?? "", max: e.target.value } })
                              }
                            />
                          </label>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="mt-4">
              <Button type="button" className="!w-auto" disabled={busy} onClick={() => void saveThresholds()}>
                Save thresholds
              </Button>
            </div>
          </Section>
        </>
      ) : null}

      <Modal
        title={ratioModal ? RATIO_LABELS[ratioModal.key] || ratioModal.key : ""}
        open={ratioModal != null}
        onClose={() => setRatioModal(null)}
      >
        {ratioModal ? (
          <div className="space-y-4">
            <p className="text-3xl font-semibold text-slate-900">{formatRatioValue(ratioModal.ratio)}</p>
            <p className="text-sm text-slate-600">{translateText(ratioModal.ratio.caption)}</p>
            {ratioModal.ratio.breakdown?.length ? (
              <dl className="divide-y divide-gray-100 rounded-lg border border-gray-100">
                {ratioModal.ratio.breakdown.map((line) => (
                  <div key={line.label} className="flex justify-between gap-4 px-3 py-2 text-sm">
                    <dt className="text-slate-600">{translateText(line.label)}</dt>
                    <dd className="font-medium tabular-nums text-slate-900">
                      {typeof line.value === "number"
                        ? line.value.toLocaleString(undefined, { maximumFractionDigits: 2 })
                        : line.value}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="text-sm text-slate-500">
                <Translated text="No breakdown available — upload a workbook with GL activity." />
              </p>
            )}
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
