export type DashboardSummary = {
  pending_count: number;
  ledger_rows: number | null;
  fiscal_start_month: number;
  fiscal_start_month_name: string;
  workbook_ok: boolean;
  workbook_error: string | null;
  currencies: string[];
};

export type DashboardPayload = {
  org_name?: string;
  summary: DashboardSummary;
  pending_preview: Record<string, unknown>[];
  pl_by_period: {
    label: string;
    revenue_net: number;
    expense_net: number;
    net_pl: number;
  }[];
  trade_outstanding: {
    currency_prefix: string;
    ar_outstanding: number;
    ap_outstanding: number;
  } | null;
  balance_sheet: {
    currency_prefix: string;
    assets_net: number;
    liabilities_net: number;
    equity_net: number;
    other_equity_net: number;
    retained_earnings_label: string;
    retained_earnings_net: number;
    period_net_income: number;
    ale_balanced: boolean;
    ale_difference: number;
  } | null;
  ratios: {
    gross_margin_pct: number | null;
    operating_margin_pct: number | null;
    quick_ratio: number | null;
  } | null;
  monthly_activity: {
    labels: string[];
    debit_totals: number[];
    stacked_by_currency: { label: string; data: number[]; color: string }[];
    currency_suffix: string;
  } | null;
  income_vs_spending: {
    revenue: number;
    expenses: number;
    currency_prefix: string;
  } | null;
  meta?: { currency_view: string; currency_prefix: string };
  revenue_breakdown?: { label: string; amount: number }[];
  expense_breakdown?: { label: string; amount: number }[];
  budget_vs_actual?: {
    label: string;
    revenue_actual: number;
    revenue_budget: number;
    expense_actual: number;
    expense_budget: number;
  }[];
  cash_runway?: {
    headline: string;
    liquid_assets_proxy: number;
    payables_outstanding: number;
    currency_prefix: string;
  } | null;
  financial_forecast?: FinancialForecastPayload | null;
};

export type FinancialForecastPayload = {
  currency_prefix: string;
  horizon_periods: number;
  labels: string[];
  baseline: { revenue: number[]; expense: number[]; net_income: number[] };
  scenarios: {
    base: { revenue: number[]; expense: number[]; net: number[] };
    best: { revenue: number[]; expense: number[]; net: number[] };
    worst: { revenue: number[]; expense: number[]; net: number[] };
  };
  method_breakdown: {
    revenue: Record<string, { label: string; values: number[] }>;
    expense: Record<string, { label: string; values: number[] }>;
  };
  revenue_weights: { method: string; weight_pct: number }[];
  expense_weights: { method: string; weight_pct: number }[];
  growth_table: {
    label: string;
    revenue: number;
    expense: number;
    net_income: number;
    mom_revenue_pct: number | null;
    yoy_revenue_pct: number | null;
  }[];
  assumptions: string[];
  frameworks: { revenue: string; expense: string };
};

export type ForecastAssumption = {
  id: string;
  side: "revenue" | "expense" | "general";
  text: string;
};

export type ForecastConfig = {
  horizon_periods: number;
  revenue_methods: Record<string, { enabled: boolean; weight: number }>;
  expense_methods: Record<string, { enabled: boolean; weight: number }>;
  bottom_up: Record<string, number>;
  time_series: { yoy_growth_pct: number };
  pct_of_sales: { cogs_pct: number; marketing_pct: number; shipping_pct: number };
  historical_incremental: { overhead_annual_growth_pct: number };
  scenario: Record<string, number>;
  custom_assumptions?: ForecastAssumption[];
};
