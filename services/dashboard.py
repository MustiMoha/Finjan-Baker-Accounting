"""Build dashboard JSON payloads for the React app (no Streamlit)."""

from __future__ import annotations

import calendar
import math
from typing import Any, Mapping, Optional

import pandas as pd
from supabase import Client

import account_buckets as ab
import database as db
import financial_kpis as fkpi
import fiscal
import gl_analytics as gla
import gl_workbook_loader as gl_wb
import org

_DASH_TAIL = 0


def _safe_float(x: object) -> float:
    try:
        if pd.isna(x):
            return 0.0
    except TypeError:
        pass
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(v):
        return 0.0
    return v


def build_dashboard_payload(
    client: Client,
    secrets: Mapping[str, Any],
    *,
    currencies: Optional[list[str]] = None,
    currency_view: str = "original",
) -> dict[str, Any]:
    org.sync_org_context(client)
    org_id = org.get_current_org_id(client)
    org_row = org.fetch_organization(client, org_id)
    fy = int(db.fetch_fiscal_start_month(client))
    pending_n = db.count_pending_transactions(client)

    df, err = gl_wb.load_gl_activity_dataframe(client, secrets, tail=_DASH_TAIL)
    gl_n = len(df) if err is None else 0

    payload: dict[str, Any] = {
        "org_name": (org_row or {}).get("name"),
        "summary": {
            "pending_count": pending_n,
            "ledger_rows": gl_n if err is None else None,
            "fiscal_start_month": fy,
            "fiscal_start_month_name": calendar.month_name[fy] if 1 <= fy <= 12 else str(fy),
            "workbook_ok": err is None,
            "workbook_error": err,
            "currencies": [],
        },
        "pending_preview": [],
        "pl_by_period": [],
        "trade_outstanding": None,
        "balance_sheet": None,
        "ratios": None,
        "income_vs_spending": None,
        "revenue_breakdown": [],
        "expense_breakdown": [],
        "cash_runway": None,
        "financial_forecast": None,
    }

    if err:
        return payload

    all_currencies = (
        sorted(df["currency_iso"].dropna().astype(str).str.upper().unique().tolist()) if not df.empty else []
    )
    payload["summary"]["currencies"] = all_currencies

    inc = currencies if currencies else all_currencies
    df_vis = df.copy()
    if not df_vis.empty and inc:
        inc_u = {x.upper() for x in inc}
        df_vis = df_vis[df_vis["currency_iso"].astype(str).str.upper().isin(inc_u)]

    if df_vis.empty:
        payload["summary"]["workbook_error"] = payload["summary"]["workbook_error"] or "No rows match filters."
        return payload

    use_usd = currency_view.strip().lower() in ("usd", "reporting", "usd_reporting")
    df_work = df_vis
    debit_col, credit_col = ("debit_usd", "credit_usd") if use_usd else ("debit", "credit")
    pref = "$" if use_usd else ""

    try:
        bucket_doc = db.fetch_account_buckets_json(client)
    except Exception:
        bucket_doc = ab.default_buckets_document()

    cat = gla.category_financial_totals(
        df_work,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
    )

    payload["pending_preview"] = db.list_pending_transactions(client, status="pending")[:12]

    rev_mag = abs(_safe_float(cat["total_revenue"]))
    exp_mag = abs(_safe_float(cat["total_expenses"]))
    payload["income_vs_spending"] = {
        "revenue": rev_mag,
        "expenses": exp_mag,
        "currency_prefix": pref,
    }

    pl_df = fkpi.pl_net_by_period(
        df_work,
        fy_start_month=fy,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
    )
    if not pl_df.empty:
        payload["pl_by_period"] = [
            {
                "label": str(row["label"]),
                "revenue_net": _safe_float(row["revenue_net"]),
                "expense_net": _safe_float(row["expense_net"]),
                "net_pl": _safe_float(row["net_pl"]),
            }
            for _, row in pl_df.iterrows()
        ]

    outstanding = fkpi.trade_ar_ap_outstanding_totals(
        df_work,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
    )
    payload["trade_outstanding"] = {
        "currency_prefix": pref,
        "ar_outstanding": _safe_float(outstanding["ar_outstanding"]),
        "ap_outstanding": _safe_float(outstanding["ap_outstanding"]),
    }

    bs = fkpi.balance_sheet_snapshot(
        cat,
        df_work,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
    )
    payload["balance_sheet"] = {
        "currency_prefix": pref,
        **{k: _safe_float(v) if isinstance(v, (int, float)) else v for k, v in bs.items()},
    }

    ratios = fkpi.key_ratios(
        cat=cat,
        df=df_work,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
    )

    def _pct(x: float) -> Optional[float]:
        return None if x != x else round(float(x), 1)

    def _ratio(x: float) -> Optional[float]:
        return None if x != x else round(float(x), 3)

    payload["ratios"] = {
        "gross_margin_pct": _pct(float(ratios["gross_margin_pct"])),
        "operating_margin_pct": _pct(float(ratios["operating_margin_pct"])),
        "quick_ratio": _ratio(float(ratios["quick_ratio"])),
    }

    payload["revenue_breakdown"] = fkpi.revenue_expense_breakdown(
        df_work, debit_col=debit_col, credit_col=credit_col, bucket_doc=bucket_doc, kind="revenue"
    )[:12]
    payload["expense_breakdown"] = fkpi.revenue_expense_breakdown(
        df_work, debit_col=debit_col, credit_col=credit_col, bucket_doc=bucket_doc, kind="expense"
    )[:12]

    ap_total = _safe_float(outstanding["ap_outstanding"])
    quick_assets = fkpi.approximate_quick_assets(
        df_work,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
    )
    runway_ok = quick_assets >= ap_total if ap_total > 1e-6 else quick_assets > 0
    payload["cash_runway"] = {
        "headline": (
            "Liquid assets cover outstanding payables."
            if runway_ok
            else "Liquid assets are below outstanding payables — review cash and vendor balances."
        ),
        "liquid_assets_proxy": _safe_float(quick_assets),
        "payables_outstanding": ap_total,
        "currency_prefix": pref,
    }

    try:
        from services.financial_forecast import build_financial_forecast

        forecast_cfg = db.fetch_forecast_config_json(client)
        payload["financial_forecast"] = build_financial_forecast(
            config=forecast_cfg,
            pl_df=pl_df,
            fy_start_month=fy,
            currency_prefix=pref,
        )
    except Exception:
        payload["financial_forecast"] = None

    payload["meta"] = {"currency_view": "usd" if use_usd else "original", "currency_prefix": pref}
    return payload
