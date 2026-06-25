"""Accountant home — ratios, threshold warnings, captions."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from supabase import Client

import database as db
import financial_kpis as fkpi
import gl_workbook_loader as gl_wb
from services.dashboard import build_dashboard_payload

RATIO_CAPTIONS: dict[str, str] = {
    "current_ratio": (
        "Broader liquidity cushion. Compare to your industry — too high can mean idle cash; too low raises solvency risk."
    ),
    "net_profit_margin": (
        "Share of revenue left as profit after all expenses. Falling margins may signal rising costs or pricing pressure."
    ),
    "return_on_equity": (
        "How effectively the business generates profit from shareholder equity. Higher ROE generally indicates stronger returns."
    ),
    "debt_to_equity": (
        "Leverage relative to equity. Higher values mean more debt financing versus owner capital."
    ),
    "interest_coverage": (
        "Ability to pay interest from operating earnings. Below 1.5 may signal difficulty covering interest obligations."
    ),
    "quick_ratio": (
        "Can you cover short-term bills without selling inventory? Below 1.0 means cash + receivables may not cover payables."
    ),
    "asset_turnover": (
        "How efficiently assets generate revenue. Higher turnover generally means better use of the balance sheet."
    ),
}

ACCOUNTANT_RATIO_KEYS = (
    "current_ratio",
    "net_profit_margin",
    "return_on_equity",
    "debt_to_equity",
    "interest_coverage",
    "quick_ratio",
    "asset_turnover",
)


def _evaluate_warnings(
    ratios: dict[str, float | None],
    thresholds: dict[str, Any],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for key, val in ratios.items():
        if val is None or val != val:
            continue
        rule = thresholds.get(key)
        if not isinstance(rule, dict):
            continue
        mn = rule.get("min")
        mx = rule.get("max")
        try:
            fv = float(val)
            if mn is not None and fv < float(mn):
                warnings.append(
                    {
                        "metric": key,
                        "level": "warning",
                        "message": f"{key.replace('_', ' ')} is {fv:.2f}, below minimum {float(mn):.2f}.",
                    }
                )
            if mx is not None and fv > float(mx):
                warnings.append(
                    {
                        "metric": key,
                        "level": "warning",
                        "message": f"{key.replace('_', ' ')} is {fv:.2f}, above maximum {float(mx):.2f}.",
                    }
                )
        except (TypeError, ValueError):
            continue
    return warnings


def build_accountant_home_payload(
    client: Client,
    secrets: Mapping[str, Any],
    *,
    currency_view: str = "original",
) -> dict[str, Any]:
    dash = build_dashboard_payload(client, secrets, currency_view=currency_view)
    thresholds = db.fetch_ratio_thresholds_json(client)

    df, err = gl_wb.load_gl_activity_dataframe(client, secrets, tail=0)
    ratios: dict[str, dict[str, Any]] = {}
    if err is None and df is not None and not df.empty:
        use_usd = currency_view.strip().lower() in ("usd", "reporting", "usd_reporting")
        debit_col, credit_col = ("debit_usd", "credit_usd") if use_usd else ("debit", "credit")
        try:
            import account_buckets as ab

            bucket_doc = db.fetch_account_buckets_json(client)
        except Exception:
            import account_buckets as ab

            bucket_doc = ab.default_buckets_document()
        import gl_analytics as gla

        cat = gla.category_financial_totals(
            df,
            debit_col=debit_col,
            credit_col=credit_col,
            bucket_doc=bucket_doc,
        )
        raw = fkpi.accountant_ratios_with_breakdown(
            cat=cat,
            df=df,
            debit_col=debit_col,
            credit_col=credit_col,
            bucket_doc=bucket_doc,
        )
        for key in ACCOUNTANT_RATIO_KEYS:
            item = raw.get(key) or {}
            ratios[key] = {
                "value": item.get("value"),
                "caption": RATIO_CAPTIONS.get(key, ""),
                "unit": item.get("unit", ""),
                "breakdown": item.get("breakdown") or [],
            }
    else:
        for key in ACCOUNTANT_RATIO_KEYS:
            ratios[key] = {
                "value": None,
                "caption": RATIO_CAPTIONS.get(key, ""),
                "unit": "%" if key in ("net_profit_margin", "return_on_equity") else "",
                "breakdown": [],
            }

    flat_for_warn = {
        k: (v["value"] if isinstance(v, dict) else None) for k, v in ratios.items()
    }
    warnings = _evaluate_warnings(flat_for_warn, thresholds)

    return {
        "org_name": dash.get("org_name"),
        "summary": dash.get("summary"),
        "ratios": ratios,
        "thresholds": thresholds,
        "warnings": warnings,
        "meta": dash.get("meta"),
    }
