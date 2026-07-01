import { useCallback, useEffect, useState } from "react";
import { Alert } from "../components/Alert";
import { Button } from "../components/Button";
import { InputField } from "../components/InputField";
import { PageHeader } from "../components/PageHeader";
import { Section } from "../components/Section";
import { Translated } from "../components/Translated";
import { useAuthTokens } from "../hooks/useAuthTokens";
import { ApiError, fetchForecastConfig, fetchForecastPreview, patchForecastConfig } from "../lib/api";
import { formatMoney } from "../lib/charts";
import type { FinancialForecastPayload, ForecastAssumption, ForecastConfig } from "../types/dashboard";
import { ForecastPageSkeleton } from "../components/Skeleton";

function newAssumptionId() {
  return `assumption-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function CustomAssumptionsEditor({
  items,
  onChange,
}: {
  items: ForecastAssumption[];
  onChange: (next: ForecastAssumption[]) => void;
}) {
  const add = () => {
    onChange([...items, { id: newAssumptionId(), side: "general", text: "" }]);
  };

  const update = (id: string, patch: Partial<ForecastAssumption>) => {
    onChange(items.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  };

  const remove = (id: string) => {
    onChange(items.filter((row) => row.id !== id));
  };

  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">
        <Translated text="Add narrative assumptions for revenue, expenses, or general notes. These appear in the forecast preview and on the admin dashboard." />
      </p>
      {items.length === 0 ? (
        <p className="text-sm text-slate-500">
          <Translated text="No custom assumptions yet." />
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((row) => (
            <li
              key={row.id}
              className="flex flex-wrap items-start gap-2 rounded-lg border border-gray-100 bg-slate-50/60 px-3 py-2"
            >
              <select
                className="rounded border border-gray-200 bg-white px-2 py-1.5 text-sm text-slate-700"
                value={row.side}
                onChange={(e) =>
                  update(row.id, { side: e.target.value as ForecastAssumption["side"] })
                }
              >
                <option value="revenue">Revenue</option>
                <option value="expense">Expense</option>
                <option value="general">General</option>
              </select>
              <input
                type="text"
                className="min-w-[12rem] flex-1 rounded border border-gray-200 px-2 py-1.5 text-sm"
                placeholder="e.g. New product launch adds 8% to Q3 revenue"
                value={row.text}
                onChange={(e) => update(row.id, { text: e.target.value })}
              />
              <button
                type="button"
                className="text-xs font-medium text-red-600 hover:underline"
                onClick={() => remove(row.id)}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <Button type="button" variant="secondary" className="!w-auto" onClick={add}>
        Add assumption
      </Button>
    </div>
  );
}

const REVENUE_METHODS = [
  { id: "bottom_up", label: "Bottom-up (traffic, conversion, AOV, sales capacity)" },
  { id: "time_series", label: "Time series (seasonality + YoY trend)" },
] as const;

const EXPENSE_METHODS = [
  { id: "pct_of_sales", label: "Percentage of sales (COGS, marketing, shipping)" },
  { id: "historical_incremental", label: "Historical / incremental (fixed overhead growth)" },
  { id: "scenario", label: "Scenario-based (feeds best / base / worst cases)" },
] as const;

function MethodToggles({
  title,
  methods,
  configKey,
  cfg,
  onChange,
}: {
  title: string;
  methods: readonly { id: string; label: string }[];
  configKey: "revenue_methods" | "expense_methods";
  cfg: ForecastConfig;
  onChange: (next: ForecastConfig) => void;
}) {
  const block = cfg[configKey] || {};
  return (
    <div className="space-y-3">
      <p className="text-sm font-semibold text-slate-800">
        <Translated text={title} />
      </p>
      {methods.map((m) => {
        const row = block[m.id] || { enabled: false, weight: 0 };
        return (
          <div key={m.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-100 bg-slate-50/60 px-3 py-2">
            <label className="flex flex-1 items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={Boolean(row.enabled)}
                onChange={(e) =>
                  onChange({
                    ...cfg,
                    [configKey]: {
                      ...block,
                      [m.id]: { ...row, enabled: e.target.checked },
                    },
                  })
                }
              />
              <Translated text={m.label} />
            </label>
            <label className="text-xs text-slate-500">
              <Translated text="Weight %" />
              <input
                type="number"
                min={0}
                max={100}
                className="ml-1 w-16 rounded border border-gray-200 px-2 py-1 text-sm"
                value={row.weight ?? 0}
                onChange={(e) =>
                  onChange({
                    ...cfg,
                    [configKey]: {
                      ...block,
                      [m.id]: { ...row, weight: Number(e.target.value) },
                    },
                  })
                }
              />
            </label>
          </div>
        );
      })}
    </div>
  );
}

export function ForecastPage() {
  const tokens = useAuthTokens();
  const [cfg, setCfg] = useState<ForecastConfig | null>(null);
  const [preview, setPreview] = useState<FinancialForecastPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);

  const load = useCallback(async () => {
    if (!tokens) return;
    try {
      const c = await fetchForecastConfig(tokens);
      setCfg(c);
      const p = await fetchForecastPreview(tokens);
      setPreview(p);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load forecast settings");
    } finally {
      setInitialLoading(false);
    }
  }, [tokens]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    if (!tokens || !cfg) return;
    setBusy(true);
    setMessage(null);
    try {
      await patchForecastConfig(tokens, cfg);
      setMessage("Forecast configuration saved. Admin dashboard will use the updated methods.");
      const p = await fetchForecastPreview(tokens);
      setPreview(p);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  };

  const refreshPreview = async () => {
    if (!tokens) return;
    setBusy(true);
    try {
      if (cfg) await patchForecastConfig(tokens, cfg);
      setPreview(await fetchForecastPreview(tokens));
      setMessage("Preview updated.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Preview failed");
    } finally {
      setBusy(false);
    }
  };

  if (initialLoading && !cfg) {
    return <ForecastPageSkeleton />;
  }

  if (!cfg) {
    return null;
  }

  const prefix = preview?.currency_prefix ?? "";

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        title="Financial forecast"
        subtitle="Configure revenue and expense forecasting methods. The reconciled baseline appears on the admin dashboard."
      />

      {message ? <Alert tone="success">{message}</Alert> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}

      <Section title="Forecast horizon">
        <label className="text-sm text-slate-600">
          <Translated text="Periods ahead" />
          <input
            type="number"
            min={3}
            max={24}
            className="ml-2 rounded border border-gray-200 px-2 py-1"
            value={cfg.horizon_periods}
            onChange={(e) => setCfg({ ...cfg, horizon_periods: Number(e.target.value) })}
          />
        </label>
      </Section>

      <Section title="Revenue forecasting">
        <MethodToggles
          title="Revenue forecasting"
          methods={REVENUE_METHODS}
          configKey="revenue_methods"
          cfg={cfg}
          onChange={setCfg}
        />
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <InputField
            label="Monthly traffic"
            type="number"
            value={String(cfg.bottom_up?.monthly_traffic ?? "")}
            onChange={(e) =>
              setCfg({ ...cfg, bottom_up: { ...cfg.bottom_up, monthly_traffic: Number(e.target.value) } })
            }
          />
          <InputField
            label="Conversion rate %"
            type="number"
            value={String(cfg.bottom_up?.conversion_rate_pct ?? "")}
            onChange={(e) =>
              setCfg({ ...cfg, bottom_up: { ...cfg.bottom_up, conversion_rate_pct: Number(e.target.value) } })
            }
          />
          <InputField
            label="Average order value"
            type="number"
            value={String(cfg.bottom_up?.average_order_value ?? "")}
            onChange={(e) =>
              setCfg({ ...cfg, bottom_up: { ...cfg.bottom_up, average_order_value: Number(e.target.value) } })
            }
          />
          <InputField
            label="Sales headcount"
            type="number"
            value={String(cfg.bottom_up?.sales_headcount ?? "")}
            onChange={(e) =>
              setCfg({ ...cfg, bottom_up: { ...cfg.bottom_up, sales_headcount: Number(e.target.value) } })
            }
          />
          <InputField
            label="Quota per rep"
            type="number"
            value={String(cfg.bottom_up?.quota_per_rep ?? "")}
            onChange={(e) =>
              setCfg({ ...cfg, bottom_up: { ...cfg.bottom_up, quota_per_rep: Number(e.target.value) } })
            }
          />
          <InputField
            label="YoY growth % (time series)"
            type="number"
            value={String(cfg.time_series?.yoy_growth_pct ?? "")}
            onChange={(e) =>
              setCfg({ ...cfg, time_series: { yoy_growth_pct: Number(e.target.value) } })
            }
          />
        </div>
      </Section>

      <Section title="Custom assumptions">
        <CustomAssumptionsEditor
          items={cfg.custom_assumptions ?? []}
          onChange={(custom_assumptions) => setCfg({ ...cfg, custom_assumptions })}
        />
      </Section>

      <Section title="Expense forecasting">
        <MethodToggles
          title="Expense forecasting"
          methods={EXPENSE_METHODS}
          configKey="expense_methods"
          cfg={cfg}
          onChange={setCfg}
        />
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <InputField
            label="COGS % of revenue"
            type="number"
            value={String(cfg.pct_of_sales?.cogs_pct ?? "")}
            onChange={(e) =>
              setCfg({ ...cfg, pct_of_sales: { ...cfg.pct_of_sales, cogs_pct: Number(e.target.value) } })
            }
          />
          <InputField
            label="Marketing % of revenue"
            type="number"
            value={String(cfg.pct_of_sales?.marketing_pct ?? "")}
            onChange={(e) =>
              setCfg({ ...cfg, pct_of_sales: { ...cfg.pct_of_sales, marketing_pct: Number(e.target.value) } })
            }
          />
          <InputField
            label="Shipping % of revenue"
            type="number"
            value={String(cfg.pct_of_sales?.shipping_pct ?? "")}
            onChange={(e) =>
              setCfg({ ...cfg, pct_of_sales: { ...cfg.pct_of_sales, shipping_pct: Number(e.target.value) } })
            }
          />
          <InputField
            label="Fixed overhead annual growth %"
            type="number"
            value={String(cfg.historical_incremental?.overhead_annual_growth_pct ?? "")}
            onChange={(e) =>
              setCfg({
                ...cfg,
                historical_incremental: { overhead_annual_growth_pct: Number(e.target.value) },
              })
            }
          />
        </div>
        <p className="mt-4 text-sm font-medium text-slate-700">
          <Translated text="Scenario multipliers (best / worst cases)" />
        </p>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          {(
            [
              ["best_revenue_mult", "Best case revenue ×"],
              ["worst_revenue_mult", "Worst case revenue ×"],
              ["best_expense_mult", "Best case expense ×"],
              ["worst_expense_mult", "Worst case expense ×"],
            ] as const
          ).map(([key, label]) => (
            <InputField
              key={key}
              label={label}
              type="number"
              step="0.01"
              value={String(cfg.scenario?.[key] ?? "")}
              onChange={(e) =>
                setCfg({ ...cfg, scenario: { ...cfg.scenario, [key]: Number(e.target.value) } })
              }
            />
          ))}
        </div>
      </Section>

      {preview ? (
        <Section title="Preview — reconciled baseline">
          <ul className="mb-4 list-disc space-y-1 pl-5 text-sm text-slate-600">
            {preview.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 text-xs uppercase text-slate-500">
                  <th className="py-2 pr-4">
                    <Translated text="Period" />
                  </th>
                  <th className="py-2 pr-4">
                    <Translated text="Revenue" />
                  </th>
                  <th className="py-2 pr-4">
                    <Translated text="Expense" />
                  </th>
                  <th className="py-2 pr-4">
                    <Translated text="Net" />
                  </th>
                  <th className="py-2 pr-4">
                    <Translated text="MoM rev %" />
                  </th>
                  <th className="py-2">
                    <Translated text="YoY rev %" />
                  </th>
                </tr>
              </thead>
              <tbody>
                {preview.growth_table.map((row) => (
                  <tr key={row.label} className="border-b border-gray-50">
                    <td className="py-2 pr-4 font-medium">{row.label}</td>
                    <td className="py-2 pr-4 tabular-nums">{formatMoney(prefix, row.revenue)}</td>
                    <td className="py-2 pr-4 tabular-nums">{formatMoney(prefix, row.expense)}</td>
                    <td className="py-2 pr-4 tabular-nums">{formatMoney(prefix, row.net_income)}</td>
                    <td className="py-2 pr-4 tabular-nums">{row.mom_revenue_pct ?? "—"}</td>
                    <td className="py-2 tabular-nums">{row.yoy_revenue_pct ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      ) : null}

      <div className="flex flex-wrap gap-3">
        <Button type="button" disabled={busy} onClick={() => void save()}>
          Save configuration
        </Button>
        <Button type="button" variant="secondary" className="!w-auto" disabled={busy} onClick={() => void refreshPreview()}>
          Refresh preview
        </Button>
      </div>
    </div>
  );
}
