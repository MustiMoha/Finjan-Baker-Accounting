"""Landing dashboard: pending queue + workbook-sourced GL analytics (Storage)."""

from __future__ import annotations

import calendar
import math
from collections import defaultdict
from datetime import date

import pandas as pd
import streamlit as st

import database as db
import excel_engine as xleng
import financial_kpis as fkpi
import fiscal
import gl_analytics as gla
import gl_workbook_loader as gl_wb
import account_buckets as ab
from components import js_charts, t_accounts

_DASH_TAIL = 0  # 0 ⇒ full GL ingest (balances inactive payables vs recent-only heuristic)

_OPENING_LEDGER_LABELS = frozenset({gla.BEGINNING_BALANCE_LABEL, gla.BROUGHT_FORWARD_LABEL})


def _is_opening_ledger_line(desc: object) -> bool:
    d = str(desc or "").strip()
    if d in _OPENING_LEDGER_LABELS:
        return True
    return gla.is_opening_or_brought_forward_rec({"description": d, "account": ""})

_STACK_PALETTE = ["#14b8a6", "#0d9488", "#5eead4", "#115e59", "#2dd4bf", "#134e4a", "#ccfbf1", "#042f2e"]


def _safe_fin_float(x: object) -> float:
    """Coerce ledger/currency inputs to a finite float (missing → 0)."""
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


def _ledger_net_balance_in_presentation(
    ledger: pd.DataFrame,
    *,
    use_usd: bool,
    presentation_iso: str,
    fx_rates_foreign_to_usd: dict[str, float],
) -> pd.DataFrame:
    """Replace ``net`` / ``balance`` with amounts in ``presentation_iso`` (FX from Configuration)."""
    pres = (presentation_iso or "USD").strip().upper()[:3]
    if len(pres) != 3:
        pres = "USD"
    merged = {**db.default_fx_rates_usd_per_unit(), **(fx_rates_foreign_to_usd or {})}
    out = ledger.copy()
    nets: list[float] = []
    balances: list[float] = []
    running = 0.0
    for _, row in out.iterrows():
        desc = str(row.get("description") or "")
        if use_usd:
            deb = _safe_fin_float(row["debit"])
            cre = _safe_fin_float(row["credit"])
            mult = _safe_fin_float(
                db.get_conversion_rate("USD", pres, table_rates_foreign_to_usd=merged)
            )
            if mult <= 0:
                mult = 1.0
            deb_p, cre_p = deb * mult, cre * mult
        else:
            oc = str(row.get("currency_iso") or "USD").strip().upper()
            oc = oc[:3] if len(oc) >= 3 else "USD"
            deb = _safe_fin_float(row["debit"])
            cre = _safe_fin_float(row["credit"])
            mult = _safe_fin_float(db.get_conversion_rate(oc, pres, table_rates_foreign_to_usd=merged))
            if mult <= 0:
                mult = 1.0
            deb_p, cre_p = deb * mult, cre * mult
        if _is_opening_ledger_line(desc):
            running = deb_p - cre_p
            nets.append(0.0)
            balances.append(running)
            continue
        net = deb_p - cre_p
        running += net
        nets.append(net)
        balances.append(running)
    out["net"] = nets
    out["balance"] = balances
    return out


def _account_ledger_totals_row(
    ledger: pd.DataFrame,
    *,
    use_usd: bool,
    presentation_iso: str,
    fx_rates_foreign_to_usd: dict[str, float],
) -> tuple[dict[str, object], str | None]:
    """
    Footer row: debit/credit/net/balance **sums in presentation currency**
    (matches recomputed ``net`` / ``balance`` on ``ledger``).
    """
    iso_pres = (presentation_iso or "USD").strip().upper()[:3]
    if len(iso_pres) != 3:
        iso_pres = "USD"

    if ledger.empty:
        total_doc = {
            "gl_date": "",
            "description": "Total",
            "account": "",
            "debit": xleng.format_amount_display(0.0, iso_pres),
            "credit": xleng.format_amount_display(0.0, iso_pres),
            "net": xleng.format_amount_display(0.0, iso_pres),
            "balance": xleng.format_amount_display(0.0, iso_pres),
        }
        return total_doc, None

    merged = {**db.default_fx_rates_usd_per_unit(), **(fx_rates_foreign_to_usd or {})}
    td = 0.0
    tc = 0.0
    for _, row in ledger.iterrows():
        if _is_opening_ledger_line(row.get("description")):
            continue
        if use_usd:
            mult = _safe_fin_float(
                db.get_conversion_rate("USD", iso_pres, table_rates_foreign_to_usd=merged)
            )
            if mult <= 0:
                mult = 1.0
            td += _safe_fin_float(row["debit"]) * mult
            tc += _safe_fin_float(row["credit"]) * mult
        else:
            oc = str(row.get("currency_iso") or "USD").strip().upper()
            oc = oc[:3] if len(oc) >= 3 else "USD"
            mult = _safe_fin_float(
                db.get_conversion_rate(oc, iso_pres, table_rates_foreign_to_usd=merged)
            )
            if mult <= 0:
                mult = 1.0
            td += _safe_fin_float(row["debit"]) * mult
            tc += _safe_fin_float(row["credit"]) * mult

    tn = float(ledger["net"].sum())
    end_bal = float(ledger["balance"].iloc[-1])

    total_doc = {
        "gl_date": "",
        "description": "Total",
        "account": "",
        "debit": xleng.format_amount_display(td, iso_pres),
        "credit": xleng.format_amount_display(tc, iso_pres),
        "net": xleng.format_amount_display(tn, iso_pres),
        "balance": xleng.format_amount_display(end_bal, iso_pres),
    }
    if "currency_iso" in ledger.columns:
        total_doc["currency_iso"] = iso_pres
    return total_doc, None


def _ledger_amount_debit(row: pd.Series, *, use_usd: bool) -> float:
    return _safe_fin_float(row.get("debit_usd")) if use_usd else _safe_fin_float(row.get("debit"))


def _ledger_amount_credit(row: pd.Series, *, use_usd: bool) -> float:
    return _safe_fin_float(row.get("credit_usd")) if use_usd else _safe_fin_float(row.get("credit"))


def _txn_ordered_fps_and_row_positions(show: pd.DataFrame) -> tuple[list[str], dict[str, list[int]]]:
    """First-seen order of journal fingerprints; map fingerprint → row indices in ``show``."""
    fp_to_idxs: dict[str, list[int]] = defaultdict(list)
    ordered: list[str] = []
    seen: set[str] = set()
    for i in range(len(show)):
        fp = db.gl_transaction_fingerprint(show.iloc[i].to_dict())
        fp_to_idxs[fp].append(i)
        if fp not in seen:
            seen.add(fp)
            ordered.append(fp)
    return ordered, fp_to_idxs


def _first_debit_row_position(show: pd.DataFrame, positions: list[int], *, use_usd: bool) -> int:
    """Row index in ``show`` for the first debit leg (journal line order when available)."""
    lines = show.iloc[positions].copy()
    lines["_pos"] = positions
    if "journal_line_in_entry" in lines.columns:
        lines = lines.sort_values("journal_line_in_entry", kind="stable")
    eps = 1e-9
    for _, row in lines.iterrows():
        if _ledger_amount_debit(row, use_usd=use_usd) > eps:
            return int(row["_pos"])
    return int(lines.iloc[0]["_pos"])


def _unique_account_labels_ci(series: pd.Series) -> list[str]:
    """One canonical spelling per account when names differ only by case / Unicode form."""
    raw = (
        series.astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )
    seen: set[str] = set()
    out: list[str] = []
    for a in sorted(raw, key=lambda s: ab.fold_account_key(str(s))):
        label = str(a).strip()
        if not label:
            continue
        k = ab.fold_account_key(label)
        if k in seen:
            continue
        seen.add(k)
        out.append(label)
    return out


def _tb_rows_for_t_accounts(tb: pd.DataFrame) -> list[dict[str, object]]:
    """Serialize trial balance for T-account cards."""
    if tb.empty:
        return []
    rows: list[dict[str, object]] = []
    for r in tb.itertuples(index=False):
        row: dict[str, object] = {
            "account": str(r.account),
            "debits": float(r.debits),
            "credits": float(r.credits),
            "net_balance": float(r.net_balance),
        }
        if hasattr(r, "opening_balance"):
            row["opening_balance"] = float(r.opening_balance)
        if hasattr(r, "opening_label"):
            row["opening_label"] = str(r.opening_label or "")
        rows.append(row)
    return rows


def _render_t_accounts_overview(
    *,
    fy: int,
    month_labels: list[str],
    fp_lookup: dict[str, tuple[int, int]],
    df_work: pd.DataFrame,
    debit_col: str,
    credit_col: str,
    bucket_doc: dict | None,
    pref: str,
) -> None:
    """Grid of summary T-accounts (one card per trial-balance account)."""
    with st.container(border=True):
        st.subheader("T-accounts")
        st.caption(
            "One classic T per trial-balance bucket — debit totals on the left, credit totals on the right. "
            "Rows labelled **Brought forward** or **Beginning balance** are opening positions (not period activity). "
            "With fiscal periods selected, **beginning balance** is cumulative through the prior month; "
            "**balance** is the closing position at the end of the selected months."
        )
        tac_f1, tac_f2, tac_f3 = st.columns([2, 1, 1])
        with tac_f1:
            tac_search = st.text_input(
                "Filter by name",
                value="",
                key="dash_tac_search",
                placeholder="e.g. cash, payable, 100",
            )
        with tac_f2:
            tac_sort = st.selectbox(
                "Sort by",
                ["Account name", "Most activity", "Largest debit balance"],
                key="dash_tac_sort",
            )
        with tac_f3:
            show_zero = st.checkbox("Include zero-activity accounts", key="dash_tac_zero")

        tac_periods = st.multiselect(
            "Fiscal periods (optional)",
            options=month_labels,
            key="dash_tac_periods",
            help="Leave empty to use every loaded period.",
        )
        set_tac = {fp_lookup[m] for m in tac_periods} if tac_periods else set()
        tb_tac = gla.trial_balance(
            df_work,
            debit_col=debit_col,
            credit_col=credit_col,
            bucket_doc=bucket_doc,
            fiscal_periods=set_tac if set_tac else None,
            fiscal_start_month=int(fy),
        )
        cards = _tb_rows_for_t_accounts(tb_tac)
        q = (tac_search or "").strip().casefold()
        if q:
            cards = [c for c in cards if q in str(c["account"]).casefold()]
        if not show_zero:
            cards = [
                c
                for c in cards
                if abs(float(c["debits"])) > 1e-9
                or abs(float(c["credits"])) > 1e-9
                or abs(float(c.get("opening_balance") or 0)) > 1e-9
            ]
        if tac_sort == "Most activity":
            cards.sort(
                key=lambda c: float(c["debits"]) + float(c["credits"]),
                reverse=True,
            )
        elif tac_sort == "Largest debit balance":
            cards.sort(key=lambda c: abs(float(c["net_balance"])), reverse=True)
        else:
            cards.sort(key=lambda c: str(c["account"]).casefold())

        if not cards:
            st.info("No accounts match these filters.")
        else:
            st.caption(f"Showing **{len(cards)}** account{'s' if len(cards) != 1 else ''}.")
            t_accounts.t_accounts_summary_grid(cards, currency_prefix=pref)


def _render_ft_hero(*, ledger_lines: int | None, workbook_ok: bool) -> None:
    today_s = date.today().strftime("%B %d, %Y")
    if workbook_ok and ledger_lines is not None and ledger_lines > 0:
        row_blurb = f"Numbers use <strong>{ledger_lines:,}</strong> journal lines from your linked Excel workbook."
    elif workbook_ok:
        row_blurb = "Your linked workbook loaded, but no journal lines were found yet."
    else:
        row_blurb = "Connect a workbook in Settings to drive these numbers."
    st.markdown(
        f"""
<div class="ft-hero">
  <div class="ft-hero-top">
    <span class="ft-pill">Live</span>
    <span class="ft-pill-muted">{today_s}</span>
  </div>
  <h1 class="ft-hero-title">Accounting overview</h1>
  <p class="ft-hero-sub">
    {row_blurb}
  </p>
</div>
        """.strip(),
        unsafe_allow_html=True,
    )


def _viewer_link_active() -> bool:
    return bool(st.session_state.get("share_viewer_lock"))


def _render_primary_financial_sections(
    df_work: pd.DataFrame,
    *,
    fy: int,
    debit_col: str,
    credit_col: str,
    cat: dict,
    pref: str,
    bucket_doc: dict | None,
    month_labels: list[str],
    fp_lookup: dict[str, tuple[int, int]],
) -> None:
    """Cash flow, period trends, AR/AP, balance sheet, ratios — main dashboard body."""
    st.subheader("Cash flow")

    cash_month_sel: list[str] = []
    if month_labels:
        cash_month_sel = st.multiselect(
            "Fiscal months for the daily chart (cash-like accounts)",
            options=month_labels,
            default=[],
            key="dash_cash_daily_month_filter",
            help="Leave empty to include every loaded row. Pick one or more months to show only those days in the bar chart.",
        )
    periods_cash = {fp_lookup[m] for m in cash_month_sel} if cash_month_sel else set()
    df_cash = fkpi.filter_gl_by_fiscal_periods(df_work, periods_cash) if periods_cash else df_work

    daily = fkpi.cash_flow_daily_net(
        df_cash, debit_col=debit_col, credit_col=credit_col, bucket_doc=bucket_doc
    )
    fc = fkpi.naive_cash_forecast(daily, (30, 60, 90))
    if periods_cash:
        net_cf = float(daily.sum()) if len(daily) else 0.0
        recent_note = "Net change across the selected fiscal months."
    else:
        net_cf = float(daily.tail(90).sum()) if len(daily) else 0.0
        recent_note = "Sum of the last ~90 days of daily net change on cash-like rows."

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Cash-like accounts (recent movement)", f"{pref}{net_cf:,.2f}", help=recent_note)
    with k2:
        st.metric("Estimate — next 30 days", f"{pref}{fc['next_30d']:,.2f}")
    with k3:
        st.metric("Estimate — next 60 days", f"{pref}{fc['next_60d']:,.2f}")
    with k4:
        st.metric("Estimate — next 90 days", f"{pref}{fc['next_90d']:,.2f}")
    cap_parts = [
        "Projection from recent daily averages on cash/bank-style accounts "
        "(including **bank** / **cash** bucket rules from Settings)."
    ]
    if periods_cash:
        cap_parts.append("Chart and headline movement use **only** the fiscal months you selected.")
    st.caption(" ".join(cap_parts))

    if len(daily) > 1:
        s = daily.sort_index()
        if not periods_cash and len(s) > 365:
            s = s.tail(365)
        s = s.reset_index()
        if len(s.columns) >= 2:
            s.columns = ["day", "net"]
        day_labels = [str(x) for x in s["day"].tolist()]
        chart_title = (
            "Daily change — cash-like accounts (selected fiscal months)"
            if periods_cash
            else "Daily change — cash-like accounts"
        )
        js_charts.bar_chart(
            day_labels,
            [float(x) for x in s["net"].tolist()],
            title=chart_title,
            height=380,
        )

    st.subheader("Income & costs by period")
    pl_df = fkpi.pl_net_by_period(
        df_work,
        fy_start_month=int(fy),
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
    )
    if pl_df.empty:
        st.info("No income or expense totals found for this view.")
    else:
        labels_p = [str(x) for x in pl_df["label"].tolist()]
        js_charts.line_chart(
            labels_p,
            {
                "Income": ([float(x) for x in pl_df["revenue_net"].tolist()], "#14b8a6"),
                "Spending": ([float(x) for x in pl_df["expense_net"].tolist()], "#f43f5e"),
                "Difference": ([float(x) for x in pl_df["net_pl"].tolist()], "#64748b"),
            },
            title="Income vs spending vs difference (by period)",
            height=440,
        )
        with st.expander("Numbers behind the chart"):
            st.dataframe(pl_df, width="stretch", hide_index=True)

    st.subheader("Accounts receivable & accounts payable")
    ao = pd.to_datetime(df_work["gl_date"], errors="coerce").max()
    as_of_date = ao.date() if pd.notna(ao) else date.today()
    ar_df, ap_df = fkpi.ar_ap_age_proxy(
        df_work,
        debit_col=debit_col,
        credit_col=credit_col,
        as_of=as_of_date,
        bucket_doc=bucket_doc,
    )
    ac1, ac2 = st.columns(2)

    def _aging_display(df_summary: pd.DataFrame, *, bar_color: str) -> None:
        filled = fkpi.ar_ap_age_buckets_filled(df_summary)
        labels_b = [str(x) for x in filled["bucket"].tolist()]
        vals_b = [float(x) for x in filled["amount"].tolist()]
        tot = sum(vals_b)
        pct = [(float(v) / tot * 100.0) if tot > 1e-12 else 0.0 for v in vals_b]
        amt_hdr = "Amount" + (f" ({pref.strip()})" if pref and pref.strip() else "")
        tbl = pd.DataFrame(
            {
                "Age bucket": labels_b,
                amt_hdr: vals_b,
                "% of total": [round(p, 1) for p in pct],
            }
        )
        js_charts.horizontal_bar_chart(
            labels_b,
            vals_b,
            title="Amount by bucket",
            dataset_label="Estimated balance",
            color=bar_color,
            height=280,
        )
        st.dataframe(
            tbl,
            width="stretch",
            hide_index=True,
            column_config={
                "Age bucket": st.column_config.TextColumn("Age bucket"),
                amt_hdr: st.column_config.NumberColumn("Amount", format="%.2f"),
                "% of total": st.column_config.NumberColumn("% of total", format="%.1f"),
            },
        )

    with ac1:
        st.markdown("**Accounts receivable** (estimate by age)")
        if ar_df.empty:
            st.info("No accounts receivable pattern detected.")
        else:
            _aging_display(ar_df, bar_color=_STACK_PALETTE[0])
    with ac2:
        st.markdown("**Accounts payable** (estimate by age)")
        if ap_df.empty:
            st.info("No accounts payable pattern detected.")
        else:
            _aging_display(ap_df, bar_color=_STACK_PALETTE[1])
    st.caption(
        f"Based on ledger activity through **{as_of_date}**. "
        "All four age buckets are shown (zeros included). Horizontal bars scale off the largest bucket — "
        "use the table for **small buckets**. Proxy only (journal dates × line nets), not open-item subledgers."
    )

    st.subheader("Balance sheet")
    bs = fkpi.balance_sheet_kpis(cat)
    b1, b2, b3 = st.columns(3)
    with b1:
        st.metric("Assets (estimate)", f"{pref}{bs['assets_net']:,.2f}")
    with b2:
        st.metric("Liabilities (estimate)", f"{pref}{bs['liabilities_net']:,.2f}")
    with b3:
        st.metric("Equity (estimate)", f"{pref}{bs['equity_net']:,.2f}")

    st.subheader("Ratios")
    ratios = fkpi.key_ratios(
        cat=cat,
        df=df_work,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
    )
    r1, r2, r3 = st.columns(3)

    def _fmt_pct(x: float) -> str:
        if x != x:
            return "N/A"
        return f"{x:.1f}%"

    def _fmt_ratio(x: float) -> str:
        if x != x:
            return "N/A"
        return f"{x:.3f}"

    with r1:
        st.metric("Gross margin (estimate)", _fmt_pct(float(ratios["gross_margin_pct"])))
    with r2:
        st.metric("Operating margin (estimate)", _fmt_pct(float(ratios["operating_margin_pct"])))
    with r3:
        st.metric("Quick ratio (estimate)", _fmt_ratio(float(ratios["quick_ratio"])))


def render(client) -> None:
    viewer_mode = _viewer_link_active()
    pending_n = db.count_pending_transactions(client) if not viewer_mode else None
    fy = db.fetch_fiscal_start_month(client)
    with st.spinner("Loading your workbook…"):
        df, err = gl_wb.get_session_gl_activity_dataframe(client, st.secrets, tail=_DASH_TAIL)
    gl_n = len(df) if err is None else 0
    _render_ft_hero(ledger_lines=gl_n if err is None else None, workbook_ok=err is None)

    pending_n_display = "—" if viewer_mode else pending_n

    with st.container(border=True):
        st.subheader("At a glance")
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric(
                "Waiting for approval",
                pending_n_display,
                help=None if not viewer_mode else "Hidden in shared view.",
            )
        with m2:
            st.metric("Ledger rows loaded", gl_n if err is None else "—")
        with m3:
            st.metric(
                "Fiscal year starts in",
                calendar.month_name[int(fy)] if 1 <= int(fy) <= 12 else str(fy),
            )
        fc1, _ = st.columns([3, 1])
        with fc1:
            currencies = (
                sorted(df["currency_iso"].dropna().astype(str).str.upper().unique().tolist())
                if err is None and not df.empty
                else []
            )
            inc = st.multiselect(
                "Currencies to include",
                options=currencies if currencies else ["—"],
                default=currencies if currencies else [],
                help="Charts only use rows in the currencies you pick here.",
                key="dash_ccy_filter",
                disabled=not currencies,
            )

    df_vis = df.copy()
    if err is None and not df_vis.empty and inc:
        df_vis = df_vis[df_vis["currency_iso"].astype(str).str.upper().isin([x.upper() for x in inc])]

    if not viewer_mode:
        with st.container(border=True):
            st.subheader("Waiting for approval")
            pending_rows = db.list_pending_transactions(client, status="pending")[:12]
            if pending_rows:
                prefer_order = [
                    "created_at",
                    "description",
                    "amount",
                    "currency_iso",
                    "debit_account",
                    "credit_account",
                    "posting_date",
                    "status",
                ]
                keys = set(pending_rows[0].keys())
                col_order = [c for c in prefer_order if c in keys]
                df_kw: dict = {"width": "stretch", "hide_index": True}
                if col_order:
                    df_kw["column_order"] = col_order
                st.dataframe(pending_rows, **df_kw)
            else:
                st.info("Nothing waiting — you're caught up.")
    if err:
        with st.container(border=True):
            st.subheader("Ledger connection")
            st.warning(err)
        return
    if df_vis.empty:
        with st.container(border=True):
            st.subheader("Ledger connection")
            st.info("No rows match your filters, or the sheet is empty. Check **Settings**.")
        return

    view_mode = str(st.session_state.get("dashboard_currency_view") or "Original Currency")
    use_usd = view_mode.startswith("USD") or "Reporting" in view_mode

    with st.container(border=True):
        st.subheader("Currencies in this window")
        ccy_grp = (
            df_vis.assign(_iso=df_vis["currency_iso"].astype(str).str.upper())
            .groupby("_iso", as_index=False)
            .agg(lines=("debit", "count"), debit_total=("debit", "sum"), credit_total=("credit", "sum"))
            .rename(columns={"_iso": "Currency"})
        )
        st.dataframe(ccy_grp, width="stretch", hide_index=True)

    if use_usd:
        df_work = df_vis
        debit_col, credit_col = "debit_usd", "credit_usd"
    else:
        df_work = df_vis
        debit_col, credit_col = "debit", "credit"

    try:
        bucket_doc = db.fetch_account_buckets_json(client)
    except Exception:
        bucket_doc = ab.default_buckets_document()

    tb = gla.trial_balance(
        df_work,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
        fiscal_periods=None,
        fiscal_start_month=int(fy),
    )

    agg = df_work.groupby(["fiscal_year", "fiscal_period"], as_index=False).agg(
        total=(debit_col, "sum"),
        lines=(debit_col, "count"),
    )
    agg["label"] = [
        fiscal.fiscal_period_calendar_label(int(r.fiscal_year), int(r.fiscal_period), int(fy))
        for r in agg.itertuples(index=False)
    ]
    agg = agg.sort_values(["fiscal_year", "fiscal_period"])

    deb_stack = "debit_usd" if use_usd else "debit"
    stack = (
        df_vis.assign(iso_u=df_vis["currency_iso"].astype(str).str.upper())
        .groupby(["fiscal_year", "fiscal_period", "iso_u"], as_index=False)
        .agg(raw_debits=(deb_stack, "sum"))
        .sort_values(["fiscal_year", "fiscal_period"])
    )
    stack["label"] = [
        fiscal.fiscal_period_calendar_label(int(r.fiscal_year), int(r.fiscal_period), int(fy))
        for r in stack.itertuples(index=False)
    ]

    month_labels = [str(x) for x in agg["label"].tolist()]
    month_totals = [float(x) for x in agg["total"].tolist()]
    fp_lookup: dict[str, tuple[int, int]] = {
        str(row.label): (int(row.fiscal_year), int(row.fiscal_period)) for row in agg.itertuples(index=False)
    }

    if not viewer_mode and month_labels:
        with st.container(border=True):
            st.subheader("Compare periods")
            sel_cmp = st.multiselect(
                "Fiscal months",
                options=month_labels,
                default=month_labels,
                key="dash_cmp_months",
            )
            set_cmp = {fp_lookup[m] for m in sel_cmp} if sel_cmp else set()
            df_cmp = fkpi.filter_gl_by_fiscal_periods(df_work, set_cmp) if set_cmp else df_work.copy()

            cat_lbls = ["Expenditures", "Income", "Assets", "Liabilities"]
            _cmp_colors = [
                "#14b8a6",
                "#f43f5e",
                "#6366f1",
                "#eab308",
                "#a855f7",
                "#0ea5e9",
                "#f97316",
                "#22c55e",
                "#ec4899",
                "#84cc16",
                "#64748b",
            ]

            def _row_vals(c_dict: dict[str, float]) -> list[float]:
                return [
                    float(c_dict["total_expenses"]),
                    float(c_dict["total_revenue"]),
                    float(c_dict["assets_net"]),
                    float(c_dict["liabilities_net"]),
                ]

            chart_series: list[tuple[str, list[float], str]] = []
            tbl_cols: dict[str, object] = {"Category": cat_lbls}

            if sel_cmp:
                months_ordered = sorted(sel_cmp, key=lambda m: fp_lookup[m])
                for i, mlab in enumerate(months_ordered):
                    df_m = fkpi.filter_gl_by_fiscal_periods(df_work, {fp_lookup[mlab]})
                    cat_m = gla.category_financial_totals(
                        df_m,
                        debit_col=debit_col,
                        credit_col=credit_col,
                        bucket_doc=bucket_doc,
                    )
                    vals = _row_vals(cat_m)
                    chart_series.append((mlab, vals, _cmp_colors[i % len(_cmp_colors)]))
                    tbl_cols[mlab] = vals
            else:
                cat_c = gla.category_financial_totals(
                    df_cmp,
                    debit_col=debit_col,
                    credit_col=credit_col,
                    bucket_doc=bucket_doc,
                )
                vals = _row_vals(cat_c)
                chart_series.append(("All loaded periods", vals, _cmp_colors[0]))
                tbl_cols["All loaded periods"] = vals

            js_charts.multi_series_grouped_bar_chart(
                cat_lbls,
                chart_series,
                title="",
                height=400,
            )
            snap_tbl = pd.DataFrame(tbl_cols)
            st.dataframe(snap_tbl, width="stretch", hide_index=True)

    with st.container(border=True):
        cat = gla.category_financial_totals(
            df_work,
            debit_col=debit_col,
            credit_col=credit_col,
            bucket_doc=bucket_doc,
        )
        st.subheader("Income & spending snapshot")
        pref = "$" if use_usd else ""
        r1a, r1b, r1c = st.columns(3)
        with r1a:
            st.metric("Total income", f"{pref}{cat['total_revenue']:,.2f}")
        with r1b:
            st.metric("Total spending", f"{pref}{cat['total_expenses']:,.2f}")
        with r1c:
            st.metric("Capital (net)", f"{pref}{cat['capital_net']:,.2f}")
        r2a, r2b, r2c = st.columns(3)
        with r2a:
            st.metric("Equity (net)", f"{pref}{cat['equity_net']:,.2f}")
        with r2b:
            st.metric("Assets (net)", f"{pref}{cat['assets_net']:,.2f}")
        with r2c:
            st.metric("Liabilities (net)", f"{pref}{cat['liabilities_net']:,.2f}")

        rev_mag = max(0.0, float(cat["total_revenue"]))
        exp_mag = max(0.0, float(cat["total_expenses"]))
        slices_lbl: list[str] = []
        slices_val: list[float] = []
        if rev_mag > 1e-9:
            slices_lbl.append("Income")
            slices_val.append(rev_mag)
        if exp_mag > 1e-9:
            slices_lbl.append("Spending")
            slices_val.append(exp_mag)

        zsum = float(tb["net_balance"].sum()) if not tb.empty else 0.0
        with st.expander("Account totals check", expanded=False):
            st.dataframe(tb, width="stretch", hide_index=True)
            st.caption(f"Sum of balances: {zsum:,.6f} — should be close to zero.")

        if slices_lbl:
            js_charts.doughnut_chart(
                slices_lbl,
                slices_val,
                ["#14b8a6", "#f43f5e"][: len(slices_lbl)],
                title="Income vs spending (relative size)",
                height=420,
            )
            if cat["total_revenue"] < 0 or cat["total_expenses"] < 0:
                st.caption("One side is negative; slices show positive amounts only.")
        elif rev_mag <= 1e-9 and exp_mag <= 1e-9:
            st.info("No income or spending found for this chart.")

    _render_primary_financial_sections(
        df_work,
        fy=int(fy),
        debit_col=debit_col,
        credit_col=credit_col,
        cat=cat,
        pref=pref,
        bucket_doc=bucket_doc,
        month_labels=month_labels,
        fp_lookup=fp_lookup,
    )

    _render_t_accounts_overview(
        fy=int(fy),
        month_labels=month_labels,
        fp_lookup=fp_lookup,
        df_work=df_work,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
        pref=pref,
    )

    with st.container(border=True):
        st.subheader("Look up one account")
        tb_lookup = gla.trial_balance(
            df_work,
            debit_col=debit_col,
            credit_col=credit_col,
            bucket_doc=bucket_doc,
            fiscal_periods=None,
            fiscal_start_month=int(fy),
        )
        lookup_opts: list[str] = []
        if not tb_lookup.empty:
            seen_lbl: set[str] = set()
            for lab in tb_lookup["account"].astype(str).tolist():
                s = str(lab).strip()
                if not s:
                    continue
                k = ab.fold_bucket_key(s)
                if k in seen_lbl:
                    continue
                seen_lbl.add(k)
                lookup_opts.append(s)
            lookup_opts.sort(key=lambda x: ab.fold_bucket_key(x))
        tac1, tac2 = st.columns([2, 1])
        with tac1:
            pick_acc = st.selectbox(
                "Pick an account (trial-balance bucket)",
                [""] + lookup_opts,
                index=0,
                key="t_acc_pick",
            )
        with tac2:
            fz = st.checkbox(
                "Match part of the name (unmapped only)",
                key="t_acc_fuzzy",
                help="When the label is a rolled-up A/P or A/R bucket, all matching sub-accounts are included automatically.",
            )
        if pick_acc:
            pick_periods = st.multiselect(
                "Fiscal periods for this account (optional)",
                options=month_labels,
                key="dash_lookup_acc_periods",
                help="Leave empty to include every loaded period. Matches labels used elsewhere on this page.",
            )
            set_lookup = {fp_lookup[m] for m in pick_periods} if pick_periods else set()

            ledger = gla.t_account_lines(
                df_work,
                pick_acc,
                fuzzy=fz,
                debit_col=debit_col,
                credit_col=credit_col,
                bucket_doc=bucket_doc,
                fiscal_periods=set_lookup if set_lookup else None,
                fiscal_start_month=int(fy),
            )
            if ledger.empty:
                st.info(
                    "No lines for this account"
                    + (" in the selected periods." if set_lookup else ".")
                )
            else:
                try:
                    fx_tbl = db.fetch_fx_rates_json(client)
                except Exception:
                    fx_tbl = {}
                pres_iso = db.fetch_display_currency_iso(client)

                ledger = _ledger_net_balance_in_presentation(
                    ledger,
                    use_usd=use_usd,
                    presentation_iso=pres_iso,
                    fx_rates_foreign_to_usd=fx_tbl,
                )

                sub_accts = sorted(
                    {
                        str(x).strip()
                        for x in ledger["account"].astype(str).tolist()
                        if str(x).strip()
                    },
                    key=lambda s: ab.fold_account_key(s),
                )
                st.markdown(f"**Running total ·** `{pick_acc}`")
                if len(sub_accts) > 1:
                    st.caption(
                        f"**{len(sub_accts)}** ledger sub-accounts in this bucket: "
                        + ", ".join(f"`{a}`" for a in sub_accts[:12])
                        + (" …" if len(sub_accts) > 12 else "")
                    )
                st.caption(
                    f"**Net**, **balance**, and the **Total** row are in **{pres_iso.strip().upper()[:3]}** "
                    "(Settings display currency × Configuration FX). Debit/Credit follow the toolbar currency view."
                )

                tac_entries: list[dict[str, object]] = []
                for _, row in ledger.iterrows():
                    desc = str(row.get("description") or "")
                    if _is_opening_ledger_line(desc):
                        tac_entries.append(
                            {
                                "description": desc,
                                "debit": _safe_fin_float(row.get("debit")),
                                "credit": _safe_fin_float(row.get("credit")),
                            }
                        )
                        continue
                    sub_a = str(row.get("account") or "").strip()
                    if sub_a and len(sub_accts) > 1:
                        desc = f"{sub_a} — {desc}" if desc else sub_a
                    tac_entries.append(
                        {
                            "description": desc,
                            "debit": _safe_fin_float(row.get("debit")),
                            "credit": _safe_fin_float(row.get("credit")),
                        }
                    )
                period_mask = ~ledger["description"].astype(str).map(_is_opening_ledger_line)
                tot_d = float(ledger.loc[period_mask, "debit"].sum()) if period_mask.any() else 0.0
                tot_c = float(ledger.loc[period_mask, "credit"].sum()) if period_mask.any() else 0.0
                end_bal = float(ledger["balance"].iloc[-1]) if len(ledger) else 0.0
                t_accounts.t_account_detail(
                    pick_acc,
                    tac_entries,
                    total_debits=tot_d,
                    total_credits=tot_c,
                    net_balance=end_bal,
                    currency_prefix=pref,
                )

                total_doc, _ = _account_ledger_totals_row(
                    ledger,
                    use_usd=use_usd,
                    presentation_iso=pres_iso,
                    fx_rates_foreign_to_usd=fx_tbl,
                )

                disp = ledger.drop(columns=["debit_usd", "credit_usd"], errors="ignore").copy()
                disp = disp.drop(columns=[c for c in ("fiscal_year", "fiscal_period") if c in disp.columns])
                pres_fmt = pres_iso.strip().upper()[:3] if len((pres_iso or "").strip()) >= 3 else "USD"
                if use_usd:
                    disp["debit"] = disp["debit"].map(
                        lambda x: xleng.format_amount_display(_safe_fin_float(x), "USD")
                    )
                    disp["credit"] = disp["credit"].map(
                        lambda x: xleng.format_amount_display(_safe_fin_float(x), "USD")
                    )
                elif "currency_iso" in disp.columns:
                    def _fmt_amt_row(r: pd.Series, col: str) -> str:
                        iso = str(r.get("currency_iso") or "USD").upper()[:3]
                        return xleng.format_amount_display(_safe_fin_float(r[col]), iso)

                    disp["debit"] = disp.apply(lambda r: _fmt_amt_row(r, "debit"), axis=1)
                    disp["credit"] = disp.apply(lambda r: _fmt_amt_row(r, "credit"), axis=1)
                else:
                    disp["debit"] = disp["debit"].map(
                        lambda x: xleng.format_amount_display(_safe_fin_float(x), "USD")
                    )
                    disp["credit"] = disp["credit"].map(
                        lambda x: xleng.format_amount_display(_safe_fin_float(x), "USD")
                    )

                disp["net"] = disp["net"].map(
                    lambda x: xleng.format_amount_display(_safe_fin_float(x), pres_fmt)
                )
                disp["balance"] = disp["balance"].map(
                    lambda x: xleng.format_amount_display(_safe_fin_float(x), pres_fmt)
                )

                disp_out = pd.concat([disp, pd.DataFrame([total_doc])], ignore_index=True)
                st.dataframe(disp_out, width="stretch", hide_index=True)

    with st.container(border=True):
        st.subheader("Activity by month")
        st.caption(f"Fiscal year starts in **{calendar.month_name[int(fy)]}**.")

        js_charts.bar_chart(
            month_labels,
            month_totals,
            title="Total debits each month",
            height=400,
        )

        js_charts.line_chart(
            month_labels,
            {"Total debits": (month_totals, "#0f766e")},
            title="How debits change over time",
            height=360,
        )

        stack_title = "Debits stacked by currency" + (" (US dollars)" if use_usd else "")
        ordered_labels = month_labels
        if stack.empty:
            st.info("No stacked currency data for this range.")
        else:
            wide = (
                stack.pivot_table(index="label", columns="iso_u", values="raw_debits", aggfunc="sum")
                .fillna(0.0)
                .reindex(ordered_labels)
                .fillna(0.0)
            )
            datasets_js: list[dict] = []
            for i, col in enumerate(wide.columns):
                datasets_js.append(
                    {
                        "label": str(col),
                        "data": [float(x) for x in wide[col].tolist()],
                        "backgroundColor": _STACK_PALETTE[i % len(_STACK_PALETTE)],
                    }
                )
            if datasets_js:
                js_charts.stacked_bar_chart(ordered_labels, datasets_js, title=stack_title, height=400)

        if not tb.empty:
            tb_top = (
                tb.assign(_act=tb["debits"].astype(float) + tb["credits"].astype(float))
                .sort_values("_act", ascending=False)
                .head(25)
            )
            js_charts.grouped_bar_chart(
                [str(x) for x in tb_top["account"].tolist()],
                [float(x) for x in tb_top["debits"].tolist()],
                [float(x) for x in tb_top["credits"].tolist()],
                title="Busiest accounts (debits and credits)",
                height=440,
            )

    with st.container(border=True):
        st.subheader("Transactions for the selected month")
        month_opts = ["—"] + month_labels
        pick_m = st.selectbox(
            "Show rows for",
            options=month_opts,
            key="dash_month_txn_filter",
        )
        if pick_m == "—":
            fy_sel = fp_sel = None
        else:
            fy_sel, fp_sel = fp_lookup[pick_m]

        detail = df_work.copy()
        if fy_sel is not None and fp_sel is not None:
            detail = detail[(detail["fiscal_year"] == fy_sel) & (detail["fiscal_period"] == fp_sel)]
            mlab = fiscal.fiscal_period_calendar_label(int(fy_sel), int(fp_sel), int(fy), long_month=True)
            st.markdown(f"**{mlab}**")

        st.caption(
            "Up to **100 journal lines** (most recent first). **One-time** is tagged **per journal entry** "
            "(whole debit/credit entry goes into the bucket). "
            "Admins choose **one checkbox per entry**, shown next to the **first debit line’s account**."
        )

        show = detail.sort_values(["gl_date"], ascending=False).head(100).copy().reset_index(drop=True)
        show["Month"] = [
            fiscal.fiscal_period_calendar_label(int(a), int(b), int(fy), long_month=True)
            for a, b in zip(show["fiscal_year"], show["fiscal_period"])
        ]

        ordered_fps, fp_to_idxs = _txn_ordered_fps_and_row_positions(show)

        try:
            saved_fps = db.fetch_one_time_transaction_fingerprints(client)
        except Exception:
            saved_fps = set()

        base_cols = ["gl_date", "Month", "description", "account", "currency_iso"]
        if use_usd:
            num_cols = ["debit_usd", "credit_usd", "original_currency", "original_amount"]
        else:
            num_cols = ["debit", "credit", "original_currency", "original_amount", "base_currency_amount"]
        sc = [c for c in base_cols + num_cols if c in show.columns]

        role = db.fetch_user_role(client)
        is_admin = role == "admin"

        if show.empty:
            st.info("No rows for this filter.")
        elif is_admin:
            summaries: list[dict[str, object]] = []
            for fp in ordered_fps:
                idxs = fp_to_idxs[fp]
                lead_pos = _first_debit_row_position(show, idxs, use_usd=use_usd)
                lead = show.iloc[lead_pos]
                sub = show.iloc[idxs]
                tot_deb = sum(_ledger_amount_debit(sub.iloc[j], use_usd=use_usd) for j in range(len(sub)))
                tot_cred = sum(_ledger_amount_credit(sub.iloc[j], use_usd=use_usd) for j in range(len(sub)))
                gd = lead["gl_date"]
                gd_s = str(gd)[:10] if pd.notna(gd) else ""
                summaries.append(
                    {
                        "gl_date": gd_s,
                        "description": str(lead.get("description") or ""),
                        "first_debit_account": str(lead.get("account") or ""),
                        "currency_iso": str(lead.get("currency_iso") or ""),
                        "total_debit": float(tot_deb),
                        "total_credit": float(tot_cred),
                        "lines": int(len(idxs)),
                        "One-time": fp in saved_fps,
                    }
                )

            summ_df = pd.DataFrame(summaries)
            st.markdown("##### Tag journal entries (one-time)")
            st.caption(
                "Each row is **one compound journal entry**. Checking **One-time** tags **every debit and credit line** "
                "for that entry. Entries appear once — keyed off the **first debit leg**."
            )

            txn_cc: dict = {
                "One-time": st.column_config.CheckboxColumn(
                    "One-time",
                    help="Whole journal entry (all legs) treated as non-recurring.",
                    default=False,
                ),
                "gl_date": st.column_config.TextColumn("Date", disabled=True, width="small"),
                "description": st.column_config.Column("Description", disabled=True),
                "first_debit_account": st.column_config.Column("First debit account", disabled=True),
                "currency_iso": st.column_config.TextColumn("Ccy", disabled=True, width="small"),
                "total_debit": st.column_config.NumberColumn(
                    "Σ Debit",
                    disabled=True,
                    format="%.2f",
                ),
                "total_credit": st.column_config.NumberColumn(
                    "Σ Credit",
                    disabled=True,
                    format="%.2f",
                ),
                "lines": st.column_config.NumberColumn("# Lines", disabled=True, format="%d"),
            }
            edited_summ = st.data_editor(
                summ_df,
                column_config=txn_cc,
                hide_index=True,
                width="stretch",
                key=f"dash_jtxn_ot_{pick_m}_{len(ordered_fps)}",
                num_rows="fixed",
            )

            line_disp = show[sc].copy()
            line_disp["gl_date"] = line_disp["gl_date"].apply(
                lambda x: str(x)[:10] if pd.notna(x) and str(x).strip() else ""
            )
            st.markdown("##### Journal lines (detail)")
            st.dataframe(line_disp, width="stretch", hide_index=True)

            if st.button("Save one-time marks", type="secondary", key="dash_save_otxn"):
                try:
                    if len(edited_summ) != len(ordered_fps):
                        st.error("Editor row count changed — reload and try again.")
                    else:
                        pairs = list(
                            zip(
                                ordered_fps,
                                [bool(x) for x in edited_summ["One-time"].tolist()],
                            )
                        )
                        db.sync_one_time_transaction_marks(client, pairs)
                        st.success("One-time bucket updated.")
                        st.rerun()
                except Exception as e:
                    st.error(str(e))
            st.caption(
                f"**{len(saved_fps)}** journal entr{'ies' if len(saved_fps) != 1 else 'y'} in the one-time bucket (all periods)."
            )
        else:
            mark_rows: set[int] = set()
            for fp in ordered_fps:
                if fp not in saved_fps:
                    continue
                idxs = fp_to_idxs[fp]
                lead_pos = _first_debit_row_position(show, idxs, use_usd=use_usd)
                mark_rows.add(lead_pos)
            disp = show[sc].copy()
            disp["gl_date"] = disp["gl_date"].apply(
                lambda x: str(x)[:10] if pd.notna(x) and str(x).strip() else ""
            )
            disp["One-time"] = ["Yes" if i in mark_rows else "" for i in range(len(show))]
            st.dataframe(disp, width="stretch", hide_index=True)
