"""
Dual-component financial forecast: revenue + expense (pro forma).

Lead accountant selects methods and weights in ``forecast_config_json``; admin dashboard
consumes the reconciled baseline and scenario outputs.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import pandas as pd

import fiscal


def _sanitize_custom_assumptions(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, str]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        side = str(item.get("side") or "general").strip().lower()
        if side not in ("revenue", "expense", "general"):
            side = "general"
        aid = str(item.get("id") or f"assumption-{i}").strip() or f"assumption-{i}"
        rows.append({"id": aid, "side": side, "text": text[:500]})
    return rows[:50]


def sanitize_forecast_config(config: dict[str, Any]) -> dict[str, Any]:
    """Drop removed keys (legacy CRM pipeline) so stored JSON stays compatible."""
    out = dict(config)
    rm = out.get("revenue_methods")
    if isinstance(rm, dict):
        cleaned = {k: v for k, v in rm.items() if k != "crm_pipeline"}
        out["revenue_methods"] = cleaned
    out.pop("pipeline", None)
    out["custom_assumptions"] = _sanitize_custom_assumptions(out.get("custom_assumptions"))
    return out


def _safe_float(x: object, default: float = 0.0) -> float:
    try:
        if pd.isna(x):
            return default
        v = float(x)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v):
        return default
    return v


def _advance_fiscal_period(fy: int, fp: int) -> tuple[int, int]:
    fp = int(fp)
    fy = int(fy)
    if fp >= 12:
        return fy + 1, 1
    return fy, fp + 1


def _fiscal_tuple_before(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[0] or (a[0] == b[0] and a[1] < b[1])


def _months_remaining_in_fiscal_year(fy: int, fp: int) -> int:
    """Inclusive count of periods from ``fp`` through period 12 of ``fy``."""
    return max(1, 12 - int(fp) + 1)


def _resolve_forecast_start(
    pl_df: pd.DataFrame | None,
    *,
    fy_start_month: int,
    today: date | None = None,
) -> tuple[int, int]:
    """
    First forecast period = month after the latest GL actuals, capped at today.

    Future-dated GL months must not push the forecast into the next fiscal year
    while the current year still has open months.
    """
    ref = today or date.today()
    cur = fiscal.fiscal_period_for(ref, fy_start_month)
    cur_key = (cur.fiscal_year, cur.fiscal_period)

    if pl_df is None or pl_df.empty:
        return cur_key

    last = pl_df.iloc[-1]
    last_key = (int(last["fiscal_year"]), int(last["fiscal_period"]))
    if not _fiscal_tuple_before(last_key, cur_key):
        last_key = cur_key
    return _advance_fiscal_period(*last_key)


def _period_labels_ahead(
    *,
    start_fy: int,
    start_fp: int,
    fy_start_month: int,
    count: int,
) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    fy, fp = int(start_fy), int(start_fp)
    for _ in range(max(1, int(count))):
        labels.append(
            {
                "fiscal_year": fy,
                "fiscal_period": fp,
                "label": fiscal.fiscal_period_calendar_label(fy, fp, fy_start_month),
            }
        )
        fy, fp = _advance_fiscal_period(fy, fp)
    return labels


def _enabled_weights(methods: dict[str, Any] | None) -> list[tuple[str, float]]:
    if not isinstance(methods, dict):
        return []
    rows: list[tuple[str, float]] = []
    for key, cfg in methods.items():
        if not isinstance(cfg, dict) or not cfg.get("enabled"):
            continue
        w = _safe_float(cfg.get("weight"), 0.0)
        if w > 0:
            rows.append((str(key), w))
    total = sum(w for _, w in rows)
    if total <= 0:
        return []
    return [(k, w / total) for k, w in rows]


def _bottom_up_monthly_revenue(config: dict[str, Any]) -> float:
    bu = config.get("bottom_up") if isinstance(config.get("bottom_up"), dict) else {}
    traffic = _safe_float(bu.get("monthly_traffic"))
    conv = _safe_float(bu.get("conversion_rate_pct")) / 100.0
    aov = _safe_float(bu.get("average_order_value"))
    funnel = traffic * conv * aov
    headcount = _safe_float(bu.get("sales_headcount"))
    quota = _safe_float(bu.get("quota_per_rep"))
    capacity = headcount * quota
    if funnel > 0 and capacity > 0:
        return (funnel + capacity) / 2.0
    return max(funnel, capacity)


def _seasonal_indices(pl_df: pd.DataFrame) -> dict[int, float]:
    if pl_df.empty:
        return {i: 1.0 for i in range(1, 13)}
    sub = pl_df.copy()
    sub["_fp"] = sub["fiscal_period"].astype(int)
    means = sub.groupby("_fp")["revenue_net"].mean()
    overall = float(means.mean()) if len(means) else 0.0
    if overall <= 1e-9:
        return {i: 1.0 for i in range(1, 13)}
    out: dict[int, float] = {}
    for fp in range(1, 13):
        v = float(means.get(fp, overall))
        out[fp] = max(0.25, v / overall) if overall else 1.0
    return out


def _historical_yoy_growth(pl_df: pd.DataFrame) -> float:
    if pl_df.empty or len(pl_df) < 2:
        return 0.0
    rev = pl_df["revenue_net"].astype(float).tolist()
    if len(rev) < 13:
        recent = rev[-1] if rev else 0.0
        prior = rev[-2] if len(rev) >= 2 else recent
        if abs(prior) < 1e-9:
            return 0.0
        return (recent - prior) / abs(prior)
    recent = rev[-1]
    year_ago = rev[-13]
    if abs(year_ago) < 1e-9:
        return 0.0
    return (recent - year_ago) / abs(year_ago)


def _revenue_by_method(
    method: str,
    *,
    config: dict[str, Any],
    periods: list[dict[str, Any]],
    pl_df: pd.DataFrame,
) -> list[float]:
    n = len(periods)
    if method == "bottom_up":
        monthly = _bottom_up_monthly_revenue(config)
        return [monthly] * n

    if method == "time_series":
        yoy = _safe_float((config.get("time_series") or {}).get("yoy_growth_pct")) / 100.0
        if not math.isfinite(yoy):
            yoy = _historical_yoy_growth(pl_df) if pl_df is not None and not pl_df.empty else 0.05
        seasonal = _seasonal_indices(pl_df)
        base_rev = 0.0
        if pl_df is not None and not pl_df.empty:
            base_rev = float(pl_df["revenue_net"].astype(float).tail(3).mean())
        if base_rev <= 0:
            base_rev = _bottom_up_monthly_revenue(config)
        out: list[float] = []
        for i, p in enumerate(periods):
            fp = int(p["fiscal_period"])
            season = seasonal.get(fp, 1.0)
            trend = (1.0 + yoy) ** (i + 1)
            out.append(base_rev * season * trend)
        return out

    return [0.0] * n


def _expense_by_method(
    method: str,
    *,
    config: dict[str, Any],
    periods: list[dict[str, Any]],
    revenue_forecast: list[float],
    pl_df: pd.DataFrame,
) -> list[float]:
    n = len(periods)
    if method == "pct_of_sales":
        ps = config.get("pct_of_sales") if isinstance(config.get("pct_of_sales"), dict) else {}
        ratio = (
            _safe_float(ps.get("cogs_pct"))
            + _safe_float(ps.get("marketing_pct"))
            + _safe_float(ps.get("shipping_pct"))
        ) / 100.0
        return [max(0.0, r * ratio) for r in revenue_forecast]

    if method == "historical_incremental":
        hi = config.get("historical_incremental") if isinstance(config.get("historical_incremental"), dict) else {}
        growth = _safe_float(hi.get("overhead_annual_growth_pct")) / 100.0 / 12.0
        base_exp = 0.0
        if pl_df is not None and not pl_df.empty:
            base_exp = float(pl_df["expense_net"].astype(float).tail(3).mean())
        if base_exp <= 0 and revenue_forecast:
            base_exp = revenue_forecast[0] * 0.55
        return [base_exp * ((1.0 + growth) ** (i + 1)) for i in range(n)]

    if method == "scenario":
        ps = config.get("pct_of_sales") if isinstance(config.get("pct_of_sales"), dict) else {}
        ratio = (
            _safe_float(ps.get("cogs_pct"))
            + _safe_float(ps.get("marketing_pct"))
            + _safe_float(ps.get("shipping_pct"))
        ) / 100.0
        hi = config.get("historical_incremental") if isinstance(config.get("historical_incremental"), dict) else {}
        growth = _safe_float(hi.get("overhead_annual_growth_pct")) / 100.0 / 12.0
        base_exp_hist = 0.0
        if pl_df is not None and not pl_df.empty:
            base_exp_hist = float(pl_df["expense_net"].astype(float).tail(3).mean())
        out: list[float] = []
        for i, rev in enumerate(revenue_forecast):
            variable = rev * ratio
            fixed = base_exp_hist * ((1.0 + growth) ** (i + 1))
            out.append(variable + fixed * 0.35)
        return out

    return [0.0] * n


def _weighted_series(
    method_values: dict[str, list[float]],
    weights: list[tuple[str, float]],
) -> list[float]:
    if not weights or not method_values:
        return []
    n = max(len(v) for v in method_values.values())
    out = [0.0] * n
    for key, w in weights:
        series = method_values.get(key) or []
        for i in range(n):
            out[i] += w * _safe_float(series[i] if i < len(series) else 0.0)
    return out


def _growth_table(
    labels: list[str],
    revenue: list[float],
    expense: list[float],
    historical: pd.DataFrame,
) -> list[dict[str, Any]]:
    hist_rev: dict[str, float] = {}
    if historical is not None and not historical.empty:
        for _, row in historical.iterrows():
            hist_rev[str(row["label"])] = _safe_float(row.get("revenue_net"))

    rows: list[dict[str, Any]] = []
    for i, label in enumerate(labels):
        rev = _safe_float(revenue[i] if i < len(revenue) else 0.0)
        exp = _safe_float(expense[i] if i < len(expense) else 0.0)
        prior_rev = _safe_float(revenue[i - 1] if i > 0 else 0.0)
        mom = ((rev - prior_rev) / abs(prior_rev) * 100.0) if abs(prior_rev) > 1e-9 else None
        hist = hist_rev.get(label)
        yoy = ((rev - hist) / abs(hist) * 100.0) if hist is not None and abs(hist) > 1e-9 else None
        rows.append(
            {
                "label": label,
                "revenue": rev,
                "expense": exp,
                "net_income": rev - exp,
                "mom_revenue_pct": round(mom, 1) if mom is not None else None,
                "yoy_revenue_pct": round(yoy, 1) if yoy is not None else None,
            }
        )
    return rows


def _assumptions(config: dict[str, Any], rev_weights: list[tuple[str, float]], exp_weights: list[tuple[str, float]]) -> list[str]:
    lines: list[str] = []
    bu = config.get("bottom_up") if isinstance(config.get("bottom_up"), dict) else {}
    ts = config.get("time_series") if isinstance(config.get("time_series"), dict) else {}
    ps = config.get("pct_of_sales") if isinstance(config.get("pct_of_sales"), dict) else {}
    hi = config.get("historical_incremental") if isinstance(config.get("historical_incremental"), dict) else {}
    sc = config.get("scenario") if isinstance(config.get("scenario"), dict) else {}

    if any(k == "bottom_up" for k, _ in rev_weights):
        lines.append(
            f"Bottom-up: traffic {_safe_float(bu.get('monthly_traffic')):,.0f} × "
            f"{_safe_float(bu.get('conversion_rate_pct')):.2f}% conv × "
            f"${_safe_float(bu.get('average_order_value')):,.0f} AOV; "
            f"{_safe_float(bu.get('sales_headcount')):.0f} reps × "
            f"${_safe_float(bu.get('quota_per_rep')):,.0f} quota."
        )
    if any(k == "time_series" for k, _ in rev_weights):
        lines.append(
            f"Time series: {_safe_float(ts.get('yoy_growth_pct')):.1f}% YoY growth with seasonal indices from GL history."
        )
    if any(k == "pct_of_sales" for k, _ in exp_weights):
        lines.append(
            f"Variable costs: COGS {_safe_float(ps.get('cogs_pct')):.1f}% + marketing "
            f"{_safe_float(ps.get('marketing_pct')):.1f}% + shipping {_safe_float(ps.get('shipping_pct')):.1f}% of revenue."
        )
    if any(k == "historical_incremental" for k, _ in exp_weights):
        lines.append(
            f"Fixed overhead grows {_safe_float(hi.get('overhead_annual_growth_pct')):.1f}% annually from trailing GL actuals."
        )
    if any(k == "scenario" for k, _ in exp_weights):
        lines.append(
            f"Scenarios: revenue × [{_safe_float(sc.get('worst_revenue_mult')):.2f} – "
            f"{_safe_float(sc.get('best_revenue_mult')):.2f}], expenses × "
            f"[{_safe_float(sc.get('worst_expense_mult')):.2f} – {_safe_float(sc.get('best_expense_mult')):.2f}]."
        )
    side_prefix = {"revenue": "Revenue assumption", "expense": "Expense assumption", "general": "Assumption"}
    for item in config.get("custom_assumptions") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        side = str(item.get("side") or "general").strip().lower()
        prefix = side_prefix.get(side, "Assumption")
        lines.append(f"{prefix}: {text}")
    return lines


def build_financial_forecast(
    *,
    config: dict[str, Any],
    pl_df: pd.DataFrame,
    fy_start_month: int,
    currency_prefix: str = "",
    today: date | None = None,
) -> dict[str, Any]:
    """Build reconciled forecast payload for dashboard and accountant review."""
    config = sanitize_forecast_config(config)
    horizon = max(3, min(24, int(_safe_float(config.get("horizon_periods"), 12))))

    ref = today or date.today()
    cur = fiscal.fiscal_period_for(ref, fy_start_month)
    start_fy, start_fp = _resolve_forecast_start(pl_df, fy_start_month=fy_start_month, today=ref)
    period_count = horizon
    if int(start_fy) == int(cur.fiscal_year):
        period_count = max(horizon, _months_remaining_in_fiscal_year(start_fy, start_fp))

    periods = _period_labels_ahead(
        start_fy=start_fy,
        start_fp=start_fp,
        fy_start_month=fy_start_month,
        count=period_count,
    )
    labels = [str(p["label"]) for p in periods]

    rev_weights = _enabled_weights(config.get("revenue_methods"))
    exp_weights = _enabled_weights(config.get("expense_methods"))

    rev_methods: dict[str, list[float]] = {}
    for key, _ in rev_weights:
        rev_methods[key] = _revenue_by_method(key, config=config, periods=periods, pl_df=pl_df)

    baseline_revenue = _weighted_series(rev_methods, rev_weights)
    if not baseline_revenue:
        baseline_revenue = _revenue_by_method("time_series", config=config, periods=periods, pl_df=pl_df)

    exp_methods: dict[str, list[float]] = {}
    for key, _ in exp_weights:
        exp_methods[key] = _expense_by_method(
            key,
            config=config,
            periods=periods,
            revenue_forecast=baseline_revenue,
            pl_df=pl_df,
        )

    baseline_expense = _weighted_series(exp_methods, exp_weights)
    if not baseline_expense:
        baseline_expense = _expense_by_method(
            "pct_of_sales",
            config=config,
            periods=periods,
            revenue_forecast=baseline_revenue,
            pl_df=pl_df,
        )

    sc = config.get("scenario") if isinstance(config.get("scenario"), dict) else {}
    best_rev_m = _safe_float(sc.get("best_revenue_mult"), 1.15)
    worst_rev_m = _safe_float(sc.get("worst_revenue_mult"), 0.85)
    best_exp_m = _safe_float(sc.get("best_expense_mult"), 0.95)
    worst_exp_m = _safe_float(sc.get("worst_expense_mult"), 1.12)

    scenarios = {
        "base": {
            "revenue": baseline_revenue,
            "expense": baseline_expense,
            "net": [r - e for r, e in zip(baseline_revenue, baseline_expense)],
        },
        "best": {
            "revenue": [r * best_rev_m for r in baseline_revenue],
            "expense": [e * best_exp_m for e in baseline_expense],
            "net": [],
        },
        "worst": {
            "revenue": [r * worst_rev_m for r in baseline_revenue],
            "expense": [e * worst_exp_m for e in baseline_expense],
            "net": [],
        },
    }
    scenarios["best"]["net"] = [
        r - e for r, e in zip(scenarios["best"]["revenue"], scenarios["best"]["expense"])
    ]
    scenarios["worst"]["net"] = [
        r - e for r, e in zip(scenarios["worst"]["revenue"], scenarios["worst"]["expense"])
    ]

    method_breakdown = {
        "revenue": {
            k: {"label": _method_label(k, "revenue"), "values": v} for k, v in rev_methods.items()
        },
        "expense": {
            k: {"label": _method_label(k, "expense"), "values": v} for k, v in exp_methods.items()
        },
    }

    return {
        "currency_prefix": currency_prefix,
        "horizon_periods": horizon,
        "labels": labels,
        "baseline": {
            "revenue": baseline_revenue,
            "expense": baseline_expense,
            "net_income": [r - e for r, e in zip(baseline_revenue, baseline_expense)],
        },
        "scenarios": scenarios,
        "method_breakdown": method_breakdown,
        "revenue_weights": [{"method": k, "weight_pct": round(w * 100, 1)} for k, w in rev_weights],
        "expense_weights": [{"method": k, "weight_pct": round(w * 100, 1)} for k, w in exp_weights],
        "growth_table": _growth_table(labels, baseline_revenue, baseline_expense, pl_df),
        "assumptions": _assumptions(config, rev_weights, exp_weights),
        "frameworks": {
            "revenue": "Revenue forecast (bottom-up, time series)",
            "expense": "Expense forecast (% of sales, historical incremental, scenarios)",
        },
    }


def _method_label(key: str, side: str) -> str:
    labels = {
        "bottom_up": "Bottom-up (drivers)",
        "time_series": "Time series analysis",
        "pct_of_sales": "Percentage of sales",
        "historical_incremental": "Historical / incremental",
        "scenario": "Scenario-based (base inputs)",
    }
    return labels.get(key, key.replace("_", " ").title())
