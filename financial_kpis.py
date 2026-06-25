"""GL-derived KPI sections: cash heuristic, P&L by period, AR/AP proxy aging, ratios.

All outputs are approximate (workbook journals only; no subledgers).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

import account_buckets as ab
import fiscal
from gl_analytics import (
    classify_account,
    classify_gl_row,
    split_account_code_and_title,
    template_heuristic_match,
)

# Aging buckets for AR/AP proxy charts (Unicode en-dash in labels matches Chart/tooltips).
AR_AP_AGE_BUCKET_ORDER = ("0–30", "31–60", "61–90", "90+")


def ar_ap_age_buckets_filled(summary: pd.DataFrame | None) -> pd.DataFrame:
    """Merge sparse bucket totals into a fixed four-bucket frame (zeros where missing)."""
    order = list(AR_AP_AGE_BUCKET_ORDER)
    base = pd.DataFrame({"bucket": order})
    if summary is None or summary.empty:
        return base.assign(amount=0.0)
    if "bucket" not in summary.columns or "amount" not in summary.columns:
        return base.assign(amount=0.0)
    sub = summary[["bucket", "amount"]].copy()
    sub["amount"] = pd.to_numeric(sub["amount"], errors="coerce").fillna(0.0)
    sub = sub.groupby("bucket", as_index=False)["amount"].sum()
    out = base.merge(sub, on="bucket", how="left")
    out["amount"] = pd.to_numeric(out["amount"], errors="coerce").fillna(0.0)
    return out


def filter_gl_by_fiscal_periods(df: pd.DataFrame, periods: set[tuple[int, int]]) -> pd.DataFrame:
    """Keep rows whose (`fiscal_year`, `fiscal_period`) is in `periods`. Empty `periods` means no filtering."""
    if df.empty or not periods:
        return df
    if "fiscal_year" not in df.columns or "fiscal_period" not in df.columns:
        return df
    sub = df.copy()
    sub["_fp"] = list(zip(sub["fiscal_year"].astype(int), sub["fiscal_period"].astype(int)))
    return sub[sub["_fp"].apply(lambda x: x in periods)].drop(columns=["_fp"])


def _dcols(df: pd.DataFrame, deb: str, cred: str) -> tuple[str, str]:
    if deb not in df.columns or cred not in df.columns:
        raise KeyError(f"Missing amount columns {deb!r}/{cred!r}")
    return deb, cred


def _account_in_cash_flow(account: str, bucket_doc: Any = None) -> bool:
    ctx = ab.coerce_context(bucket_doc)
    hit = ab.match_account_to_bucket(
        account, ctx, template_matcher=template_heuristic_match
    )
    if hit is not None and hit.template_key in ("bank", "cash"):
        return True
    return is_cash_like_account(account, bucket_doc)


def is_cash_like_account(account: str, bucket_doc: Any = None) -> bool:
    ctx = ab.coerce_context(bucket_doc)
    hit = ab.match_account_to_bucket(
        account, ctx, template_matcher=template_heuristic_match
    )
    if hit is not None and hit.template_key in ("bank", "cash"):
        return True
    n = ab.fold_account_key(account)
    return any(
        sub in n for sub in ("cash", "bank", "checking", "savings", "wallet", "petty cash", "clearing cash")
    )


def is_ar_account(account: str) -> bool:
    n = ab.fold_account_key(account)
    return ("receivable" in n or "a/r" in n or "accounts receivable" in n) and "payable" not in n


def is_ap_account(account: str) -> bool:
    n = ab.fold_account_key(account)
    return "payable" in n or "a/p" in n or "accounts payable" in n


def cash_flow_daily_net(
    df: pd.DataFrame,
    *,
    debit_col: str,
    credit_col: str,
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> pd.Series:
    """Net change on cash-like accounts per calendar day (debit − credit on those rows)."""
    doc = bucket_doc if bucket_doc is not None else bucket_mappings
    deb, cred = _dcols(df, debit_col, credit_col)
    if df.empty or "gl_date" not in df.columns:
        return pd.Series(dtype=float)
    dd = df.copy()
    dd["_dt"] = pd.to_datetime(dd["gl_date"], errors="coerce")
    dd = dd[dd["_dt"].notna()]
    mask = dd["account"].astype(str).apply(lambda a: _account_in_cash_flow(a, doc))
    sub = dd.loc[mask]
    if sub.empty:
        return pd.Series(dtype=float)
    sub = sub.assign(_net=sub[deb].astype(float) - sub[cred].astype(float))
    sub["_day"] = pd.to_datetime(sub["_dt"]).dt.strftime("%Y-%m-%d")
    g = sub.groupby("_day", sort=True)["_net"].sum()
    g.index = g.index.astype(str)
    return g


def naive_cash_forecast(daily_net: pd.Series, horizons: tuple[int, ...]) -> dict[str, float]:
    """Average trailing daily net × horizon days — indicative only."""
    out: dict[str, float] = {}
    if daily_net.empty:
        return {f"next_{h}d": 0.0 for h in horizons}
    trail = daily_net.tail(min(90, len(daily_net)))
    mu = float(trail.mean()) if len(trail) else 0.0
    for h in horizons:
        key = f"next_{h}d"
        out[key] = mu * float(max(h, 0))
    return out


def pl_net_by_period(
    df: pd.DataFrame,
    *,
    fy_start_month: int,
    debit_col: str,
    credit_col: str,
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> pd.DataFrame:
    """Revenue (net), expense (net), P&L net by fiscal period."""
    doc = bucket_doc if bucket_doc is not None else bucket_mappings
    deb, cred = _dcols(df, debit_col, credit_col)
    cols = ["fiscal_year", "fiscal_period", "label", "revenue_net", "expense_net", "net_pl"]
    if df.empty or "gl_date" not in df.columns:
        return pd.DataFrame(columns=cols)
    w = df.copy()
    w["_cls"] = w.apply(lambda r: classify_gl_row(r, doc), axis=1)
    w["_dt"] = pd.to_datetime(w["gl_date"], errors="coerce")
    w = w[w["_dt"].notna()]
    if w.empty:
        return pd.DataFrame(columns=cols)

    fy: list[int] = []
    fp: list[int] = []
    for t in w["_dt"]:
        d = pd.Timestamp(t).date()
        fp_t = fiscal.fiscal_period_for(d, fy_start_month)
        fy.append(fp_t.fiscal_year)
        fp.append(fp_t.fiscal_period)
    w["_fy"] = fy
    w["_fp"] = fp

    rows: list[dict[str, float | int | str]] = []
    for (fy_, fp_), grp in w.groupby(["_fy", "_fp"]):
        rev = grp[grp["_cls"] == "Revenue"]
        exp = grp[grp["_cls"] == "Expense"]
        rnet = float(rev[cred].sum() - rev[deb].sum())
        enet = float(exp[deb].sum() - exp[cred].sum())
        lbl = fiscal.fiscal_period_calendar_label(int(fy_), int(fp_), int(fy_start_month))
        rows.append(
            {
                "fiscal_year": int(fy_),
                "fiscal_period": int(fp_),
                "label": lbl,
                "revenue_net": rnet,
                "expense_net": enet,
                "net_pl": float(rnet - enet),
            }
        )
    return pd.DataFrame(rows).sort_values(["fiscal_year", "fiscal_period"]).reset_index(drop=True)


def ar_ap_age_proxy(
    df: pd.DataFrame,
    *,
    debit_col: str,
    credit_col: str,
    as_of: date | None = None,
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Bucket line-level nets on AR/AP-named accounts by age vs as-of (journal proxy, not true open items).
    """
    doc = bucket_doc if bucket_doc is not None else bucket_mappings
    deb, cred = _dcols(df, debit_col, credit_col)
    ctx = ab.coerce_context(doc)

    def row_is_ar(acct: str) -> bool:
        hit = ab.match_account_to_bucket(
            acct, ctx, template_matcher=template_heuristic_match
        )
        if hit is not None and hit.template_key == "accounts_receivable":
            return True
        return is_ar_account(acct)

    def row_is_ap(acct: str) -> bool:
        hit = ab.match_account_to_bucket(
            acct, ctx, template_matcher=template_heuristic_match
        )
        if hit is not None and hit.template_key == "accounts_payable":
            return True
        return is_ap_account(acct)
    if df.empty or "gl_date" not in df.columns:
        return pd.DataFrame(), pd.DataFrame()
    w = df.copy()
    w["_dt"] = pd.to_datetime(w["gl_date"], errors="coerce")
    w = w[w["_dt"].notna()]
    ref = pd.Timestamp(as_of).normalize() if as_of is not None else w["_dt"].max()
    if pd.isna(ref):
        return pd.DataFrame(), pd.DataFrame()

    def bucket(days: float) -> str:
        if days <= 30:
            return "0–30"
        if days <= 60:
            return "31–60"
        if days <= 90:
            return "61–90"
        return "90+"

    order = ["0–30", "31–60", "61–90", "90+"]

    def _cell_amt(cell) -> float:
        x = pd.to_numeric(cell, errors="coerce")
        return 0.0 if pd.isna(x) else float(x)

    ar_parts: list[dict[str, float | str]] = []
    for _, r in w.iterrows():
        if not row_is_ar(str(r["account"])):
            continue
        nets = _cell_amt(r[deb]) - _cell_amt(r[cred])
        age_days = int((ref - pd.Timestamp(r["_dt"]).normalize()).days)
        ar_parts.append({"bucket": bucket(float(age_days)), "amount": abs(nets)})

    ap_parts: list[dict[str, float | str]] = []
    for _, r in w.iterrows():
        if not row_is_ap(str(r["account"])):
            continue
        nets = _cell_amt(r[cred]) - _cell_amt(r[deb])
        age_days = int((ref - pd.Timestamp(r["_dt"]).normalize()).days)
        ap_parts.append({"bucket": bucket(float(age_days)), "amount": abs(nets)})

    ar_df = (
        pd.DataFrame(ar_parts).groupby("bucket", as_index=False)["amount"].sum()
        if ar_parts
        else pd.DataFrame(columns=["bucket", "amount"])
    )
    ap_df = (
        pd.DataFrame(ap_parts).groupby("bucket", as_index=False)["amount"].sum()
        if ap_parts
        else pd.DataFrame(columns=["bucket", "amount"])
    )

    def _order(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df["_o"] = df["bucket"].apply(lambda x: order.index(str(x)) if str(x) in order else 99)
        return df.sort_values("_o").drop(columns=["_o"])

    return _order(ar_df), _order(ap_df)


def balance_sheet_kpis(cat: dict[str, float]) -> dict[str, float]:
    return {
        "assets_net": float(cat.get("assets_net") or 0),
        "liabilities_net": float(cat.get("liabilities_net") or 0),
        "equity_net": float(cat.get("equity_net") or 0),
    }


def trade_ar_ap_outstanding_totals(
    df: pd.DataFrame,
    *,
    debit_col: str,
    credit_col: str,
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> dict[str, float]:
    """Closing trade A/R and A/P balances from trial balance (no aging buckets)."""
    import gl_analytics as gla

    doc = bucket_doc if bucket_doc is not None else bucket_mappings
    tb = gla.trial_balance(df, debit_col=debit_col, credit_col=credit_col, bucket_doc=doc)
    ar = 0.0
    ap = 0.0
    if tb.empty:
        return {"ar_outstanding": 0.0, "ap_outstanding": 0.0}
    for _, row in tb.iterrows():
        acct = str(row["account"])
        nb = float(row.get("net_balance") or 0.0)
        if gla.is_trade_accounts_receivable_line(acct, doc):
            ar += max(nb, 0.0)
        elif gla.is_trade_accounts_payable_line(acct, doc):
            ap += max(-nb, 0.0)
    return {"ar_outstanding": ar, "ap_outstanding": ap}


def balance_sheet_snapshot(
    cat: dict[str, float],
    df: pd.DataFrame,
    *,
    debit_col: str,
    credit_col: str,
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> dict[str, float | bool | str]:
    """
    Balance-sheet headline totals with retained earnings / accumulated deficit for A = L + E.
    """
    import gl_analytics as gla

    doc = bucket_doc if bucket_doc is not None else bucket_mappings
    assets = float(cat.get("assets_net") or 0)
    liabilities = float(cat.get("liabilities_net") or 0)
    equity_net = float(cat.get("equity_net") or 0)
    period_net = float(cat.get("total_revenue") or 0) - float(cat.get("total_expenses") or 0)

    tb = gla.trial_balance(df, debit_col=debit_col, credit_col=credit_col, bucket_doc=doc)
    if tb.empty:
        eq_other = pd.DataFrame()
        eq_ret = pd.DataFrame()
    else:
        cls = tb["account"].astype(str).map(lambda a: classify_account(a, doc))
        eq_tb = tb.loc[cls == "Equity"].copy()
        eq_other, eq_ret = gla.equity_rows_partition_retained(eq_tb)

    other_equity = gla.sum_equity_tb_bs_amount(eq_other)
    retained_gl = gla.sum_equity_tb_bs_amount(eq_ret)
    if not eq_ret.empty or abs(retained_gl) > 1e-9:
        retained_amount = retained_gl
    else:
        retained_amount = period_net

    retained_label = "Accumulated deficit" if retained_amount < 0 else "Retained earnings"
    # Unclosed P&L (revenue − expense) belongs on the equity side of A = L + E.
    ale_rhs = liabilities + equity_net + period_net
    ale_diff = assets - ale_rhs
    tol = max(0.01, abs(assets) * 1e-6, abs(ale_rhs) * 1e-6)

    return {
        "assets_net": assets,
        "liabilities_net": liabilities,
        "equity_net": equity_net,
        "other_equity_net": other_equity,
        "retained_earnings_label": retained_label,
        "retained_earnings_net": retained_amount,
        "period_net_income": period_net,
        "ale_balanced": abs(ale_diff) <= tol,
        "ale_difference": ale_diff,
    }


def approximate_cogs_net(df: pd.DataFrame, *, debit_col: str, credit_col: str) -> float:
    deb, cred = _dcols(df, debit_col, credit_col)
    if df.empty:
        return 0.0
    n = df["account"].astype(str).str.lower()
    mask = (
        n.str.contains("cogs", na=False)
        | n.str.contains("cost of goods", na=False)
        | n.str.contains("cost of sales", na=False)
    )
    sub = df.loc[mask]
    if sub.empty:
        return 0.0
    return float(sub[deb].sum() - sub[cred].sum())


def approximate_quick_assets(
    df: pd.DataFrame,
    *,
    debit_col: str,
    credit_col: str,
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> float:
    doc = bucket_doc if bucket_doc is not None else bucket_mappings
    tb = df.copy()
    tb["_cls"] = tb.apply(lambda r: classify_gl_row(r, doc), axis=1)
    nn = tb["account"].astype(str).str.lower()
    ar_bucket = tb["account"].astype(str).apply(
        lambda a: ab.match_bucket_kind(a, doc) == "accounts_receivable"
    )
    cash_ar_inv = tb[
        tb["_cls"].eq("Asset")
        & (
            tb["account"].astype(str).apply(lambda a: is_cash_like_account(a, doc))
            | ar_bucket
            | nn.str.contains("receivable", na=False)
            | nn.str.contains("inventory", na=False)
        )
    ]
    deb, cred = _dcols(tb, debit_col, credit_col)
    if cash_ar_inv.empty:
        return 0.0
    return float(cash_ar_inv[deb].sum() - cash_ar_inv[cred].sum())


def approximate_current_liabilities(
    df: pd.DataFrame,
    *,
    debit_col: str,
    credit_col: str,
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> float:
    doc = bucket_doc if bucket_doc is not None else bucket_mappings
    tb = df.copy()
    cls = tb.apply(lambda r: classify_gl_row(r, doc), axis=1)
    sub = tb[cls.eq("Liability")]
    deb, cred = _dcols(tb, debit_col, credit_col)
    if sub.empty:
        return 0.0
    return float(sub[cred].sum() - sub[deb].sum())


def approximate_current_assets(
    df: pd.DataFrame,
    *,
    debit_col: str,
    credit_col: str,
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> float:
    """Cash, receivables, inventory, and other short-term asset accounts."""
    doc = bucket_doc if bucket_doc is not None else bucket_mappings
    tb = df.copy()
    tb["_cls"] = tb.apply(lambda r: classify_gl_row(r, doc), axis=1)
    nn = tb["account"].astype(str).str.lower()
    ar_bucket = tb["account"].astype(str).apply(
        lambda a: ab.match_bucket_kind(a, doc) == "accounts_receivable"
    )
    current = tb[
        tb["_cls"].eq("Asset")
        & (
            tb["account"].astype(str).apply(lambda a: is_cash_like_account(a, doc))
            | ar_bucket
            | nn.str.contains("receivable", na=False)
            | nn.str.contains("inventory", na=False)
            | nn.str.contains("prepaid", na=False)
            | nn.str.contains("current asset", na=False)
        )
    ]
    deb, cred = _dcols(tb, debit_col, credit_col)
    if current.empty:
        return 0.0
    return float(current[deb].sum() - current[cred].sum())


def approximate_interest_expense(
    df: pd.DataFrame,
    *,
    debit_col: str,
    credit_col: str,
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> float:
    doc = bucket_doc if bucket_doc is not None else bucket_mappings
    if df.empty:
        return 0.0
    deb, cred = _dcols(df, debit_col, credit_col)
    cls = df.apply(lambda r: classify_gl_row(r, doc), axis=1)
    nn = df["account"].astype(str).str.lower()
    mask = cls.eq("Expense") & (
        nn.str.contains("interest", na=False)
        | nn.str.contains("finance charge", na=False)
    )
    sub = df.loc[mask]
    if sub.empty:
        return 0.0
    return float(sub[deb].sum() - sub[cred].sum())


def accountant_ratios_with_breakdown(
    *,
    cat: dict[str, float],
    df: pd.DataFrame,
    debit_col: str,
    credit_col: str,
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> dict[str, dict[str, Any]]:
    """Five accountant-home ratios with numeric components for modal breakdowns."""
    doc = bucket_doc if bucket_doc is not None else bucket_mappings
    rev = float(max(cat.get("total_revenue", 0.0), 0.0))
    expenses = float(max(cat.get("total_expenses", 0.0), 0.0))
    equity = float(cat.get("equity_net") or 0.0)
    liabilities = float(cat.get("liabilities_net") or 0.0)
    net_income = rev - expenses

    cogs = approximate_cogs_net(df, debit_col=debit_col, credit_col=credit_col)
    operating_income = (rev - cogs) - (expenses - cogs) if rev > 1e-6 else net_income
    interest = approximate_interest_expense(
        df, debit_col=debit_col, credit_col=credit_col, bucket_doc=doc
    )
    current_assets = approximate_current_assets(
        df, debit_col=debit_col, credit_col=credit_col, bucket_doc=doc
    )
    current_liabilities = approximate_current_liabilities(
        df, debit_col=debit_col, credit_col=credit_col, bucket_doc=doc
    )

    current_ratio_val = (
        float(current_assets / current_liabilities) if current_liabilities > 1e-6 else float("nan")
    )
    net_margin_val = float(100 * net_income / rev) if rev > 1e-6 else float("nan")
    roe_val = float(100 * net_income / equity) if abs(equity) > 1e-6 else float("nan")
    dte_val = float(liabilities / equity) if abs(equity) > 1e-6 else float("nan")
    ic_val = float(operating_income / interest) if interest > 1e-6 else float("nan")

    def _r(x: float, places: int = 3) -> float | None:
        return None if x != x else round(float(x), places)

    prefix = "Approximate from general ledger"
    out: dict[str, dict[str, Any]] = {
        "current_ratio": {
            "value": _r(current_ratio_val),
            "unit": "",
            "breakdown": [
                {"label": "Current assets", "value": round(current_assets, 2)},
                {"label": "Current liabilities", "value": round(current_liabilities, 2)},
                {"label": "Formula", "value": "Current assets ÷ Current liabilities"},
                {"label": "Note", "value": prefix},
            ],
        },
        "net_profit_margin": {
            "value": _r(net_margin_val, 1),
            "unit": "%",
            "breakdown": [
                {"label": "Revenue", "value": round(rev, 2)},
                {"label": "Expenses", "value": round(expenses, 2)},
                {"label": "Net income", "value": round(net_income, 2)},
                {"label": "Formula", "value": "Net income ÷ Revenue × 100"},
                {"label": "Note", "value": prefix},
            ],
        },
        "return_on_equity": {
            "value": _r(roe_val, 1),
            "unit": "%",
            "breakdown": [
                {"label": "Net income", "value": round(net_income, 2)},
                {"label": "Equity (net)", "value": round(equity, 2)},
                {"label": "Formula", "value": "Net income ÷ Equity × 100"},
                {"label": "Note", "value": prefix},
            ],
        },
        "debt_to_equity": {
            "value": _r(dte_val),
            "unit": "",
            "breakdown": [
                {"label": "Total liabilities", "value": round(liabilities, 2)},
                {"label": "Equity (net)", "value": round(equity, 2)},
                {"label": "Formula", "value": "Total liabilities ÷ Equity"},
                {"label": "Note", "value": prefix},
            ],
        },
        "interest_coverage": {
            "value": _r(ic_val),
            "unit": "",
            "breakdown": [
                {"label": "Operating income (approx.)", "value": round(operating_income, 2)},
                {"label": "Interest expense (approx.)", "value": round(interest, 2)},
                {"label": "Formula", "value": "Operating income ÷ Interest expense"},
                {"label": "Note", "value": prefix},
            ],
        },
    }

    qa = approximate_quick_assets(
        df, debit_col=debit_col, credit_col=credit_col, bucket_doc=doc
    )
    quick_ratio_val = float(qa / current_liabilities) if current_liabilities > 1e-6 else float("nan")
    assets_net = float(cat.get("assets_net") or 0.0)
    asset_turnover_val = float(rev / assets_net) if abs(assets_net) > 1e-6 else float("nan")

    out["quick_ratio"] = {
        "value": _r(quick_ratio_val),
        "unit": "",
        "breakdown": [
            {"label": "Quick assets (approx.)", "value": round(qa, 2)},
            {"label": "Current liabilities", "value": round(current_liabilities, 2)},
            {"label": "Formula", "value": "Quick assets ÷ Current liabilities"},
            {"label": "Note", "value": prefix},
        ],
    }
    out["asset_turnover"] = {
        "value": _r(asset_turnover_val),
        "unit": "",
        "breakdown": [
            {"label": "Revenue", "value": round(rev, 2)},
            {"label": "Total assets (net)", "value": round(assets_net, 2)},
            {"label": "Formula", "value": "Revenue ÷ Total assets"},
            {"label": "Note", "value": prefix},
        ],
    }
    return out


def key_ratios(
    *,
    cat: dict[str, float],
    df: pd.DataFrame,
    debit_col: str,
    credit_col: str,
    bucket_mappings: Any = None,
    bucket_doc: Any = None,
) -> dict[str, float]:
    rev = float(max(cat.get("total_revenue", 0.0), 0.0))
    rev_denom = rev if rev > 1e-6 else float("nan")
    cogs = approximate_cogs_net(df, debit_col=debit_col, credit_col=credit_col)
    expenses = float(max(cat.get("total_expenses", 0.0), 0))
    gross_num = rev - cogs if rev > 1e-6 else float("nan")
    gross_margin_pct = float(100 * gross_num / rev_denom) if rev > 1e-6 else float("nan")

    operating_income_approx = gross_num - (expenses - cogs)
    operating_margin_pct = float(100 * operating_income_approx / rev_denom) if rev > 1e-6 else float("nan")

    doc = bucket_doc if bucket_doc is not None else bucket_mappings
    qa = approximate_quick_assets(df, debit_col=debit_col, credit_col=credit_col, bucket_doc=doc)
    cl = approximate_current_liabilities(df, debit_col=debit_col, credit_col=credit_col, bucket_doc=doc)
    quick_ratio = float(qa / cl) if cl > 1e-6 else float("nan")

    return {
        "gross_margin_pct": gross_margin_pct,
        "operating_margin_pct": operating_margin_pct,
        "quick_ratio": quick_ratio,
    }


def _rollup_label(account: str, bucket_doc: Any) -> str:
    ctx = ab.coerce_context(bucket_doc)
    hit = ab.match_account_to_bucket(account, ctx, template_matcher=template_heuristic_match)
    if hit is not None and hit.name:
        return ab.canonical_bucket_display(ctx, hit.name)
    return classify_account(account, bucket_doc)


_GENERIC_EXPENSE_TEMPLATES = frozenset({"expense", ""})
_GENERIC_EXPENSE_BUCKET_NAMES = frozenset(
    {ab.fold_bucket_key("expense"), ab.fold_bucket_key("expenses")}
)


def _expense_breakdown_label(account: str, bucket_doc: Any) -> str:
    """
    Granular expense chart labels: specific expense buckets, else GL account titles.

    Avoids rolling all expense lines into one generic «Expenses» bucket.
    """
    acct = (account or "").strip()
    ctx = ab.coerce_context(bucket_doc)
    hit = ab.match_account_to_bucket(acct, ctx, template_matcher=template_heuristic_match)
    if hit is not None:
        name = str(hit.name or "").strip()
        cat = str(hit.category or "").strip().lower()
        tmpl = str(hit.template_key or "").strip().lower()
        if cat == "expense" and name and ab.fold_bucket_key(name) not in _GENERIC_EXPENSE_BUCKET_NAMES:
            if tmpl not in _GENERIC_EXPENSE_TEMPLATES:
                return ab.canonical_bucket_display(ctx, name)
    _code, title = split_account_code_and_title(acct)
    label = (title or acct).strip()
    return label or "Other expense"


def _aggregate_breakdown_rows(sub: pd.DataFrame) -> list[dict[str, float | str]]:
    """Sum amounts by case-insensitive label; keep the longest display spelling."""
    if sub.empty:
        return []
    work = sub.copy()
    work["_label_key"] = work["rollup_label"].astype(str).map(ab.fold_bucket_key)
    rows: list[dict[str, float | str]] = []
    for _key, grp in work.groupby("_label_key", sort=False):
        amount = float(grp["_net"].sum())
        if abs(amount) <= 1e-9:
            continue
        labels = [str(x).strip() for x in grp["rollup_label"].astype(str) if str(x).strip()]
        display = max(labels, key=len) if labels else "Other"
        rows.append({"label": display, "amount": amount})
    rows.sort(key=lambda r: abs(float(r["amount"])), reverse=True)
    return rows


def revenue_expense_breakdown(
    df: pd.DataFrame,
    *,
    debit_col: str,
    credit_col: str,
    bucket_doc: Any,
    kind: str,
) -> list[dict[str, float | str]]:
    """Top rollup buckets for revenue (credit-normal) or expense (debit-normal) lines."""
    if df.empty:
        return []
    deb, cred = _dcols(df, debit_col, credit_col)
    cls = df.apply(lambda r: classify_gl_row(r, bucket_doc), axis=1)
    if kind == "revenue":
        sub = df[cls.eq("Revenue")].copy()
        if sub.empty:
            return []
        sub["_net"] = sub[cred].astype(float) - sub[deb].astype(float)
    else:
        sub = df[cls.eq("Expense")].copy()
        if sub.empty:
            return []
        sub["_net"] = sub[deb].astype(float) - sub[cred].astype(float)
    if kind == "expense":
        sub["rollup_label"] = sub["account"].astype(str).apply(lambda a: _expense_breakdown_label(a, bucket_doc))
    else:
        sub["rollup_label"] = sub["account"].astype(str).apply(lambda a: _rollup_label(a, bucket_doc))
    return _aggregate_breakdown_rows(sub)


def budget_vs_actual_period(
    pl_df: pd.DataFrame,
    *,
    budget_json: dict[str, Any] | None = None,
) -> list[dict[str, float | str]]:
    """Compare period revenue/expense to stored budget or trailing average baseline."""
    if pl_df.empty:
        return []
    budgets = (budget_json or {}).get("periods") if isinstance(budget_json, dict) else None
    if not isinstance(budgets, dict):
        budgets = {}
    rows: list[dict[str, float | str]] = []
    for i in range(len(pl_df)):
        row = pl_df.iloc[i]
        label = str(row["label"])
        rev = float(row.get("revenue_net", 0) or 0)
        exp = float(row.get("expense_net", 0) or 0)
        stored = budgets.get(label) if isinstance(budgets.get(label), dict) else {}
        rev_b = stored.get("revenue") if isinstance(stored, dict) else None
        exp_b = stored.get("expenses") if isinstance(stored, dict) else None
        if rev_b is None or exp_b is None:
            prior = pl_df.iloc[:i]
            if len(prior) >= 1:
                rev_b = float(prior["revenue_net"].tail(3).mean()) if rev_b is None else rev_b
                exp_b = float(prior["expense_net"].tail(3).mean()) if exp_b is None else exp_b
            else:
                rev_b = rev if rev_b is None else rev_b
                exp_b = exp if exp_b is None else exp_b
        rows.append(
            {
                "label": label,
                "revenue_actual": rev,
                "revenue_budget": float(rev_b or 0),
                "expense_actual": exp,
                "expense_budget": float(exp_b or 0),
            }
        )
    return rows[-12:]

