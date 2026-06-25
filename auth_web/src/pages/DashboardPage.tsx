import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useLocale, useT } from "../context/LocaleContext";
import { useReloadOnWindowFocus } from "../hooks/useReloadOnWindowFocus";
import { ApiError, fetchDashboard } from "../lib/api";
import {
  BAKER_ROSE,
  BAKER_SLATE,
  BAKER_TEAL,
  Bar,
  CHART_GRID,
  DOUGHNUT_PERCENT_OPTIONS,
  Doughnut,
  doughnutPercentLabelsPlugin,
  Line,
  formatMoney,
} from "../lib/charts";
import type { DashboardPayload } from "../types/dashboard";

function MetricCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-slate-900">{value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-400">{hint}</p> : null}
    </div>
  );
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
      {subtitle ? <p className="mb-4 mt-1 text-sm text-slate-500">{subtitle}</p> : <div className="mb-4" />}
      {children}
    </section>
  );
}

type DashboardMode = "admin" | "viewer";

export function DashboardPage({ mode }: { mode: DashboardMode }) {
  const t = useT();
  const { locale, translateText, prefetchTexts } = useLocale();
  const isAdmin = mode === "admin";
  const { session } = useAuth();
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [currencyView, setCurrencyView] = useState<"original" | "usd">("original");
  const [selectedCurrencies, setSelectedCurrencies] = useState<string[]>([]);
  const [forecastPeriods, setForecastPeriods] = useState<string[]>([]);
  const [forecastScenario, setForecastScenario] = useState<"base" | "best" | "worst">("base");

  const tokens = useMemo(
    () =>
      session?.access_token && session.refresh_token
        ? { accessToken: session.access_token, refreshToken: session.refresh_token }
        : null,
    [session],
  );

  const load = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!tokens) return;
      if (!opts?.silent) {
        setLoading(true);
        setError(null);
      }
      try {
        const res = await fetchDashboard(tokens, {
          currencyView,
          currencies: selectedCurrencies.length ? selectedCurrencies : undefined,
        });
        setData(res);
        if (opts?.silent) {
          setError(null);
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not load dashboard");
      } finally {
        if (!opts?.silent) {
          setLoading(false);
        }
      }
    },
    [tokens, currencyView, selectedCurrencies],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useReloadOnWindowFocus(
    useCallback(() => {
      void load({ silent: true });
    }, [load]),
  );

  useEffect(() => {
    if (locale !== "ar" || !data) return;
    const dynamic: string[] = [];
    if (data.cash_runway?.headline) dynamic.push(data.cash_runway.headline);
    for (const r of data.revenue_breakdown ?? []) dynamic.push(r.label);
    for (const r of data.expense_breakdown ?? []) dynamic.push(r.label);
    for (const r of data.pl_by_period ?? []) dynamic.push(r.label);
    if (data.balance_sheet?.retained_earnings_label) {
      dynamic.push(data.balance_sheet.retained_earnings_label);
    }
    prefetchTexts(dynamic);
  }, [data, locale, prefetchTexts]);

  useEffect(() => {
    if (data?.summary.currencies.length && selectedCurrencies.length === 0) {
      setSelectedCurrencies(data.summary.currencies);
    }
  }, [data, selectedCurrencies.length]);

  useEffect(() => {
    if (data?.financial_forecast?.labels.length) {
      setForecastPeriods(data.financial_forecast.labels);
    }
  }, [data?.financial_forecast?.labels]);

  const filteredForecast = useMemo(() => {
    const fc = data?.financial_forecast;
    if (!fc) return null;
    const selected = new Set(forecastPeriods);
    const indices = fc.labels.map((label, i) => (selected.has(label) ? i : -1)).filter((i) => i >= 0);
    const pick = (arr: number[]) => indices.map((i) => arr[i] ?? 0);
    return {
      labels: indices.map((i) => fc.labels[i]),
      scenarios: {
        base: {
          revenue: pick(fc.baseline.revenue),
          expense: pick(fc.baseline.expense),
          net: pick(fc.baseline.net_income),
        },
        best: {
          revenue: pick(fc.scenarios.best.revenue),
          expense: pick(fc.scenarios.best.expense),
          net: pick(fc.scenarios.best.net),
        },
        worst: {
          revenue: pick(fc.scenarios.worst.revenue),
          expense: pick(fc.scenarios.worst.expense),
          net: pick(fc.scenarios.worst.net),
        },
      },
      growth_table: fc.growth_table.filter((row) => selected.has(row.label)),
    };
  }, [data?.financial_forecast, forecastPeriods]);

  const activeForecast = useMemo(() => {
    if (!filteredForecast) return null;
    return filteredForecast.scenarios[forecastScenario];
  }, [filteredForecast, forecastScenario]);

  if (loading && !data) {
    return <p className="text-sm text-slate-500">{t("dashboard.loading")}</p>;
  }

  if (error && !data) {
    return <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>;
  }

  if (!data) return null;

  const prefix =
    data.meta?.currency_prefix ??
    data.trade_outstanding?.currency_prefix ??
    data.balance_sheet?.currency_prefix ??
    "";

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            {isAdmin ? t("dashboard.executiveTitle") : t("dashboard.title")}
          </h1>
          {data.org_name ? <p className="text-sm text-slate-500">{data.org_name}</p> : null}
          {isAdmin ? (
            <p className="mt-1 max-w-xl text-sm text-slate-600">{t("dashboard.executiveQuestion")}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm text-slate-600">
            {t("dashboard.currencyView")}{" "}
            <select
              value={currencyView}
              onChange={(e) => setCurrencyView(e.target.value as "original" | "usd")}
              className="ml-1 rounded-lg border border-gray-200 px-2 py-1.5 text-sm"
            >
              <option value="original">{t("dashboard.originalCurrency")}</option>
              <option value="usd">{t("dashboard.usdReporting")}</option>
            </select>
          </label>
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-lg bg-baker-teal px-3 py-1.5 text-sm font-medium text-white hover:bg-baker-teal-dark"
          >
            {t("dashboard.refresh")}
          </button>
        </div>
      </header>

      {data.summary.workbook_error ? (
        <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {data.summary.workbook_error}
        </div>
      ) : null}

      {isAdmin && data.cash_runway ? (
        <div
          className={`rounded-xl border px-5 py-4 ${
            data.cash_runway.headline.includes("tight")
              ? "border-amber-200 bg-amber-50 text-amber-950"
              : "border-emerald-200 bg-emerald-50 text-emerald-950"
          }`}
        >
          <p className="font-medium">{translateText(data.cash_runway.headline)}</p>
          <p className="mt-1 text-sm opacity-90">
            {t("dashboard.liquidAssets")} {formatMoney(prefix, data.cash_runway.liquid_assets_proxy)} ·{" "}
            {t("dashboard.outstandingPayables")}{" "}
            {formatMoney(prefix, data.cash_runway.payables_outstanding)}
          </p>
        </div>
      ) : null}

      <div className={`grid gap-4 ${isAdmin ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
        {isAdmin ? (
          <MetricCard label={t("dashboard.waitingApproval")} value={String(data.summary.pending_count)} />
        ) : null}
        <MetricCard
          label={t("dashboard.ledgerRows")}
          value={data.summary.ledger_rows != null ? String(data.summary.ledger_rows) : "—"}
        />
        <MetricCard label={t("dashboard.fiscalYearStarts")} value={data.summary.fiscal_start_month_name} />
      </div>

      {data.income_vs_spending &&
      (data.income_vs_spending.revenue > 0 || data.income_vs_spending.expenses > 0) ? (
        <Section title={t("dashboard.incomeVsExpense")}>
          <div className="mx-auto h-80 max-w-md">
            <Doughnut
              data={{
                labels: [t("dashboard.income"), t("dashboard.expenses")],
                datasets: [
                  {
                    data: [data.income_vs_spending.revenue, data.income_vs_spending.expenses],
                    backgroundColor: [BAKER_TEAL, BAKER_ROSE],
                    borderColor: "#ffffff",
                    borderWidth: 3,
                  },
                ],
              }}
              options={DOUGHNUT_PERCENT_OPTIONS}
              plugins={[doughnutPercentLabelsPlugin]}
            />
          </div>
        </Section>
      ) : null}

      {isAdmin && (data.revenue_breakdown?.length || data.expense_breakdown?.length) ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {data.revenue_breakdown?.length ? (
            <Section title={t("dashboard.revenueBreakdown")}>
              <div className="h-72">
                <Bar
                  data={{
                    labels: data.revenue_breakdown.map((r) => translateText(r.label)),
                    datasets: [
                      {
                        label: t("dashboard.revenue"),
                        data: data.revenue_breakdown.map((r) => r.amount),
                        backgroundColor: BAKER_TEAL,
                      },
                    ],
                  }}
                  options={{
                    indexAxis: "y" as const,
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                  }}
                />
              </div>
            </Section>
          ) : null}
          {data.expense_breakdown?.length ? (
            <Section title={t("dashboard.expenseBreakdown")}>
              <div className="h-72">
                <Bar
                  data={{
                    labels: data.expense_breakdown.map((r) => translateText(r.label)),
                    datasets: [
                      {
                        label: t("dashboard.expenses"),
                        data: data.expense_breakdown.map((r) => r.amount),
                        backgroundColor: BAKER_ROSE,
                      },
                    ],
                  }}
                  options={{
                    indexAxis: "y" as const,
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                  }}
                />
              </div>
            </Section>
          ) : null}
        </div>
      ) : null}

      {isAdmin && data.pl_by_period.length > 0 ? (
        <Section title={t("dashboard.incomeCostsByPeriod")}>
          <div className="h-96">
            <Line
              data={{
                labels: data.pl_by_period.map((r) => r.label),
                datasets: [
                  {
                    label: t("dashboard.income"),
                    data: data.pl_by_period.map((r) => r.revenue_net),
                    borderColor: BAKER_TEAL,
                    tension: 0.2,
                  },
                  {
                    label: t("dashboard.expenses"),
                    data: data.pl_by_period.map((r) => r.expense_net),
                    borderColor: BAKER_ROSE,
                    tension: 0.2,
                  },
                  {
                    label: t("dashboard.difference"),
                    data: data.pl_by_period.map((r) => r.net_pl),
                    borderColor: BAKER_SLATE,
                    tension: 0.2,
                  },
                ],
              }}
              options={{
                responsive: true,
                maintainAspectRatio: false,
                scales: { x: { grid: { color: CHART_GRID } }, y: { grid: { color: CHART_GRID } } },
              }}
            />
          </div>
        </Section>
      ) : null}

      {isAdmin && data.financial_forecast && filteredForecast && activeForecast ? (
        <Section title={t("dashboard.financialForecast")}>
          <div className="mb-4">
            <p className="mb-2 text-sm font-medium text-slate-700">{t("dashboard.scenario")}</p>
            <div className="flex flex-wrap gap-2">
              {(
                [
                  { id: "base" as const, label: t("dashboard.base") },
                  { id: "best" as const, label: t("dashboard.best") },
                  { id: "worst" as const, label: t("dashboard.worst") },
                ] as const
              ).map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setForecastScenario(opt.id)}
                  className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                    forecastScenario === opt.id
                      ? opt.id === "best"
                        ? "bg-emerald-600 text-white"
                        : opt.id === "worst"
                          ? "bg-amber-500 text-white"
                          : "bg-baker-teal text-white"
                      : "border border-gray-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
          <div className="mb-4">
            <p className="mb-2 text-sm font-medium text-slate-700">{t("dashboard.periods")}</p>
            <div className="flex flex-wrap gap-2">
              {data.financial_forecast.labels.map((label) => {
                const on = forecastPeriods.includes(label);
                return (
                  <button
                    key={label}
                    type="button"
                    onClick={() =>
                      setForecastPeriods((prev) =>
                        on ? prev.filter((p) => p !== label) : [...prev, label],
                      )
                    }
                    className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                      on
                        ? "bg-baker-teal text-white"
                        : "border border-gray-200 bg-white text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
            <div className="mt-2 flex gap-2">
              <button
                type="button"
                className="text-xs font-medium text-baker-teal-dark underline"
                onClick={() => setForecastPeriods(data.financial_forecast!.labels)}
              >
                {t("dashboard.selectAll")}
              </button>
              <button
                type="button"
                className="text-xs font-medium text-slate-500 underline"
                onClick={() => setForecastPeriods([])}
              >
                {t("dashboard.clear")}
              </button>
            </div>
          </div>
          {filteredForecast.labels.length > 0 ? (
            <>
              <div className="h-96">
                <Bar
                  data={{
                    labels: filteredForecast.labels,
                    datasets: [
                      {
                        label: t("dashboard.revenue"),
                        data: activeForecast.revenue,
                        backgroundColor: BAKER_TEAL,
                        stack: "forecast",
                      },
                      {
                        label: t("dashboard.expenses"),
                        data: activeForecast.expense,
                        backgroundColor: BAKER_ROSE,
                        stack: "forecast",
                      },
                    ],
                  }}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { position: "top" as const } },
                    scales: {
                      x: { stacked: true, grid: { color: CHART_GRID } },
                      y: { stacked: true, grid: { color: CHART_GRID } },
                    },
                  }}
                />
              </div>
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-xs uppercase text-slate-500">
                      <th className="py-2 pr-3">{t("dashboard.period")}</th>
                      <th className="py-2 pr-3">{t("dashboard.revenue")}</th>
                      <th className="py-2 pr-3">{t("dashboard.expenses")}</th>
                      <th className="py-2 pr-3">{t("dashboard.momPct")}</th>
                      <th className="py-2 pr-3">{t("dashboard.yoyPct")}</th>
                      <th className="py-2">
                        {t("dashboard.net")} (
                        {forecastScenario === "base"
                          ? t("dashboard.base")
                          : forecastScenario === "best"
                            ? t("dashboard.best")
                            : t("dashboard.worst")}
                        )
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredForecast.growth_table.map((row, idx) => {
                      const rev = activeForecast.revenue[idx] ?? 0;
                      const prevRev = idx > 0 ? activeForecast.revenue[idx - 1] ?? 0 : 0;
                      const momPct =
                        idx > 0 && Math.abs(prevRev) > 1e-9
                          ? ((rev - prevRev) / Math.abs(prevRev)) * 100
                          : null;
                      return (
                        <tr key={row.label} className="border-b border-gray-50">
                          <td className="py-2 pr-3 font-medium">{row.label}</td>
                          <td className="py-2 pr-3 tabular-nums">{formatMoney(prefix, rev)}</td>
                          <td className="py-2 pr-3 tabular-nums">
                            {formatMoney(prefix, activeForecast.expense[idx] ?? 0)}
                          </td>
                          <td className="py-2 pr-3 tabular-nums">
                            {momPct != null ? momPct.toFixed(1) : "—"}
                          </td>
                          <td className="py-2 pr-3 tabular-nums">
                            {forecastScenario === "base" ? (row.yoy_revenue_pct ?? "—") : "—"}
                          </td>
                          <td className="py-2 tabular-nums">
                            {formatMoney(prefix, activeForecast.net[idx] ?? 0)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-500">{t("dashboard.selectOnePeriod")}</p>
          )}
        </Section>
      ) : null}

      {isAdmin && data.balance_sheet ? (
        <Section title={t("dashboard.balanceSheet")} subtitle={t("dashboard.balanceSheetSubtitle")}>
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <MetricCard label={t("dashboard.assets")} value={formatMoney(prefix, data.balance_sheet.assets_net)} />
              <MetricCard
                label={t("dashboard.liabilities")}
                value={formatMoney(prefix, data.balance_sheet.liabilities_net)}
              />
              <MetricCard
                label={t("dashboard.otherEquity")}
                value={formatMoney(prefix, data.balance_sheet.other_equity_net)}
              />
              <MetricCard
                label={translateText(data.balance_sheet.retained_earnings_label)}
                value={formatMoney(prefix, data.balance_sheet.retained_earnings_net)}
              />
              <MetricCard label={t("dashboard.totalEquity")} value={formatMoney(prefix, data.balance_sheet.equity_net)} />
              <MetricCard
                label={t("dashboard.periodNetIncome")}
                value={formatMoney(prefix, data.balance_sheet.period_net_income)}
                hint={t("dashboard.periodNetHint")}
              />
            </div>
            <div className="flex flex-col gap-3">
              <div className="h-48">
                <Bar
                  data={{
                    labels: [t("dashboard.assets"), t("dashboard.liabilities"), t("dashboard.equity")],
                    datasets: [
                      {
                        label: "Amount",
                        data: [
                          data.balance_sheet.assets_net,
                          data.balance_sheet.liabilities_net,
                          data.balance_sheet.equity_net,
                        ],
                        backgroundColor: [BAKER_TEAL, BAKER_ROSE, BAKER_SLATE],
                      },
                    ],
                  }}
                  options={{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                  }}
                />
              </div>
              <p
                className={`rounded-lg px-3 py-2 text-sm ${
                  data.balance_sheet.ale_balanced
                    ? "bg-emerald-50 text-emerald-900"
                    : "bg-amber-50 text-amber-950"
                }`}
              >
                {data.balance_sheet.ale_balanced
                  ? t("dashboard.aleBalanced")
                  : `${t("dashboard.aleVariance")}: ${formatMoney(prefix, data.balance_sheet.ale_difference)} — ${t("dashboard.aleHint")}`}
              </p>
            </div>
          </div>
        </Section>
      ) : null}

      {isAdmin && data.trade_outstanding ? (
        <Section title={t("dashboard.outstandingTitle")} subtitle={t("dashboard.outstandingSubtitle")}>
          <div className="grid gap-4 sm:grid-cols-2">
            <MetricCard
              label={t("dashboard.accountsReceivable")}
              value={formatMoney(prefix, data.trade_outstanding.ar_outstanding)}
            />
            <MetricCard
              label={t("dashboard.accountsPayable")}
              value={formatMoney(prefix, data.trade_outstanding.ap_outstanding)}
            />
          </div>
        </Section>
      ) : null}
    </div>
  );
}

export function AdminDashboardPage() {
  return <DashboardPage mode="admin" />;
}

export function ViewerDashboardPage() {
  return <DashboardPage mode="viewer" />;
}
