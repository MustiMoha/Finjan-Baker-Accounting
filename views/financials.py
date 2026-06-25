"""Journal-style preview from the master workbook stored in Supabase."""

from __future__ import annotations

import html
import json
import os
import urllib.request
from datetime import date
from typing import Any, Mapping

import pandas as pd
import streamlit as st

import database as db
import excel_engine as xleng
import financial_kpis as fkpi
import fiscal
import gl_analytics as gla
import gl_workbook_loader as gl_wb
import org
import statement_export as stm_exp
import supabase_storage_workbook as sbw
from ui_locale import append_locale_to_url, tr
from views import gl_sheet_editor


def _fiscal_month_labels(df: pd.DataFrame, fy_start_month: int) -> tuple[list[str], dict[str, tuple[int, int]]]:
    if df.empty or "fiscal_year" not in df.columns or "fiscal_period" not in df.columns:
        return [], {}
    parts = df[["fiscal_year", "fiscal_period"]].drop_duplicates()
    lookup: dict[str, tuple[int, int]] = {}
    for _, row in parts.iterrows():
        fy_i = int(row["fiscal_year"])
        fp_i = int(row["fiscal_period"])
        lab = fiscal.fiscal_period_calendar_label(fy_i, fp_i, fy_start_month)
        lookup[str(lab)] = (fy_i, fp_i)
    ordered = sorted(lookup.items(), key=lambda kv: kv[1])
    return [kv[0] for kv in ordered], lookup


def _resolve_has_tr_column(layout: dict[str, Any] | None, raw: list[dict[str, Any]] | None) -> bool:
    cols = (layout or {}).get("columns") if isinstance((layout or {}).get("columns"), dict) else {}
    trn = cols.get("tr_number")
    if trn is not None and str(trn).strip() != "":
        return True
    if raw:
        for r in raw[:400]:
            if r.get("transaction_number") is not None and str(r.get("transaction_number")).strip() != "":
                return True
    return False


def _render_gl_row_count_caption(
    cached_raw: list[dict[str, Any]],
    raw_for_scope: list[dict[str, Any]],
    slice_raw: list[dict[str, Any]],
    *,
    pick_months: list[str],
    n_recent: int,
    layout: dict[str, Any] | None,
) -> None:
    """Explain how many GL lines are in cache vs on screen (common source of 'missing' rows)."""
    n_cache = len(cached_raw)
    n_filtered = len(raw_for_scope)
    n_shown = len(slice_raw)
    parts = [tr(f"**{n_cache}** lines loaded from the workbook")]
    if pick_months:
        parts.append(tr(f"**{n_filtered}** after fiscal-month filter"))
    if n_recent > 0 and n_shown < n_filtered:
        parts.append(
            tr(f"**{n_shown}** shown (last **{n_recent}** rows — raise **Rows shown** or set it to **0** for all)")
        )
    elif n_shown != n_filtered:
        parts.append(tr(f"**{n_shown}** shown"))

    layout_note = ""
    if isinstance(layout, dict):
        try:
            ds = int(layout.get("data_start_row") or 0)
            hf = int(layout.get("header_first_row") or 1)
            if ds > hf + 1:
                layout_note = tr(
                    f" Reading starts at Excel row **{ds}** (Settings → workbook GL column layout). "
                    "Rows above that are skipped."
                )
        except (TypeError, ValueError):
            pass

    st.caption(
        "".join(parts)
        + layout_note
        + tr(" Click **Refresh** to reload the workbook from storage (same as reopening from Baker).")
    )


def _filter_raw_records_by_months(
    records: list[dict[str, Any]],
    fy_m: int,
    fp_lookup: dict[str, tuple[int, int]],
    pick_m: list[str],
) -> list[dict[str, Any]]:
    if not pick_m or not records:
        return records
    selected = {fp_lookup[m] for m in pick_m if m in fp_lookup}
    if not selected:
        return records

    last_d: date | None = None
    dated: list[tuple[dict[str, Any], date | None]] = []
    for r in records:
        explicit = xleng.parse_gl_cell_to_date(r.get("gl_date"))
        if explicit is not None:
            last_d = explicit
        gd = explicit if explicit is not None else last_d
        dated.append((r, gd))

    out: list[dict[str, Any]] = []
    for r, gd in dated:
        if gd is None:
            continue
        fp = fiscal.fiscal_period_for(gd, fy_m)
        if (fp.fiscal_year, fp.fiscal_period) in selected:
            out.append(r)
    return out


def _financials_cached_retained_earnings_cell(
    client,
    secrets: Mapping[str, Any],
    *,
    cache_gen: int,
    bucket: str,
    object_path: str,
    sheet_name: str,
    cell_a1: str,
) -> tuple[float | None, str | None]:
    """Read workbook retained earnings anchor once per workbook/cache/signature."""
    sig = f"{cache_gen}|{bucket}|{object_path}|{sheet_name}|{cell_a1}"
    prev = str(st.session_state.get("fin_retained_read_sig") or "")
    if prev == sig and "fin_retained_read_amount" in st.session_state:
        return (
            st.session_state.get("fin_retained_read_amount"),
            st.session_state.get("fin_retained_read_err"),
        )

    tmp_path: str | None = None
    try:
        tmp_path = sbw.download_master_to_tempfile(client, bucket, object_path)
        amt, err = xleng.read_numeric_cell_openpyxl(tmp_path, sheet_name=sheet_name, cell_a1=cell_a1)
        st.session_state["fin_retained_read_sig"] = sig
        st.session_state["fin_retained_read_amount"] = amt
        st.session_state["fin_retained_read_err"] = err
        return amt, err
    except Exception as e:
        err_s = str(e).strip() or repr(e)
        st.session_state["fin_retained_read_sig"] = sig
        st.session_state["fin_retained_read_amount"] = None
        st.session_state["fin_retained_read_err"] = err_s
        return None, err_s
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _auth_web_api_base() -> str:
    try:
        return str(st.secrets.get("AUTH_WEB_URL", "http://127.0.0.1:8000")).rstrip("/")
    except Exception:
        return "http://127.0.0.1:8000"


def _mint_streamlit_handoff_url() -> str | None:
    """One-time Baker → Streamlit handoff (re-establishes session like **Financials** in the sidebar)."""
    access = st.session_state.get("access_token")
    refresh = st.session_state.get("refresh_token")
    if not access or not refresh:
        return None
    url = f"{_auth_web_api_base()}/api/streamlit/handoff"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {access}",
            "X-Refresh-Token": str(refresh),
            "Content-Type": "application/json",
        },
        data=b"{}",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        handoff = str(data.get("url") or "").strip()
        return append_locale_to_url(handoff) or None
    except Exception:
        return None


@st.cache_data(show_spinner="Preparing GL download…")
def _fin_gl_export_xlsx(
    bucket: str,
    object_path: str,
    gl_sheet_name: str,
    workbook_cache_gen: int,
) -> tuple[bytes, str]:
    """Build a one-sheet GL .xlsx from the master workbook (cached until cache_gen changes)."""
    del workbook_cache_gen  # cache-bust key only
    client = st.session_state.get("sb")
    if client is None:
        raise RuntimeError("Sign in again to download the workbook.")
    tmp_path = None
    try:
        tmp_path = sbw.download_master_to_tempfile(client, bucket, object_path)
        out_b = stm_exp.general_ledger_sheet_exact_copy_to_xlsx_bytes(
            tmp_path, sheet_name=gl_sheet_name
        )
        safe_nm = "".join(c if c.isalnum() or c in "._-" else "_" for c in gl_sheet_name)[:48]
        return out_b, f"general_ledger_{safe_nm}.xlsx"
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _refresh_financials_page(client, secrets: Mapping[str, Any]) -> None:
    """Full reload: clear GL editor state, re-handoff from Baker when possible, refresh workbook cache."""
    gl_sheet_editor.clear_financials_gl_edit_session_state()
    _fin_gl_export_xlsx.clear()
    for key in (
        "fin_retained_read_sig",
        "fin_retained_read_amount",
        "fin_retained_read_err",
        "_fin_gl_dl_bytes",
        "_fin_gl_dl_name",
        "_fin_gl_export_gen",
    ):
        st.session_state.pop(key, None)

    handoff_url = _mint_streamlit_handoff_url()
    if handoff_url:
        st.session_state["_app_page_marker"] = ""
        safe_url = html.escape(handoff_url, quote=True)
        st.markdown(f'<meta http-equiv="refresh" content="0;url={safe_url}">', unsafe_allow_html=True)
        st.link_button(tr("Reload Financials from Baker"), handoff_url)
        st.stop()

    err = gl_wb.refresh_workbook_session_cache(client, dict(secrets))
    if err:
        st.error(err)
    else:
        st.rerun()


def _render_financial_workbook_tabs(client, role: str) -> None:
    gl_sheet_name = db.resolve_gl_sheet_name(client)
    path_secret = str(st.secrets.get("MASTER_WORKBOOK_STORAGE_PATH") or "").strip()
    object_path = db.resolve_master_workbook_file_id(client, path_secret)
    bucket = sbw.master_workbook_bucket(st.secrets)
    layout = db.fetch_gl_layout_json(client)

    if not object_path.strip():
        st.warning(tr("Add a workbook in **Settings** or set **MASTER_WORKBOOK_STORAGE_PATH** in secrets."))
        return

    refresh_c1, refresh_c2 = st.columns([1, 6])
    with refresh_c1:
        if st.button(
            tr("Refresh"),
            key="financials_refresh_workbook",
            help=tr("Re-handoff from Baker (when online) and reload the master workbook from storage."),
        ):
            _refresh_financials_page(client, dict(st.secrets))
    with refresh_c2:
        n_recent = int(
            st.number_input(
                tr("Rows shown"),
                min_value=0,
                max_value=10000,
                value=int(st.session_state.get("fin_rows_pref") or 0),
                step=50,
                help=tr(
                    "0 = every line loaded from the workbook (after fiscal-month filter). "
                    "Any positive number shows only the last N lines of that set."
                ),
                key="fin_rows_back_input",
            )
        )
        st.session_state["fin_rows_pref"] = n_recent

    cached_raw = st.session_state.get("master_gl_rows_raw")
    act_err = st.session_state.get("gl_activity_err")
    df_all = st.session_state.get("gl_activity_df")
    if isinstance(df_all, pd.DataFrame) and act_err is None and not df_all.empty:
        fy_m = db.fetch_fiscal_start_month(client)
        month_labels, fp_lookup = _fiscal_month_labels(df_all, fy_m)
    else:
        month_labels, fp_lookup = [], {}

    pick_months = st.multiselect(
        tr("Fiscal months"),
        options=month_labels,
        default=[],
        key="fin_month_filter",
    )
    set_p = {fp_lookup[m] for m in pick_months} if pick_months else set()

    is_admin = role == "admin"

    tab_gl, tab_bs, tab_is, tab_tb = st.tabs(
        [
            tr("General ledger"),
            tr("Balance sheet"),
            tr("Income statement"),
            tr("Trial balance"),
        ]
    )

    if not cached_raw:
        with tab_gl:
            if act_err:
                st.error(str(act_err))
            else:
                st.info(tr("No rows in range."))
        with tab_bs, tab_is, tab_tb:
            st.info(tr("Load the workbook to view statements."))
        return

    fy_m = db.fetch_fiscal_start_month(client)
    raw_for_scope = _filter_raw_records_by_months(cached_raw, fy_m, fp_lookup, pick_months)
    slice_raw = raw_for_scope[-n_recent:] if n_recent > 0 else raw_for_scope
    months_sig = ",".join(sorted(pick_months)) if pick_months else "_all"
    gl_scope_sig = f"m:{months_sig}|rows:{n_recent}"

    has_tr = _resolve_has_tr_column(layout if isinstance(layout, dict) else None, cached_raw)

    wcg = int(st.session_state.get("workbook_cache_gen") or 0)

    with tab_gl:
        _render_gl_row_count_caption(
            cached_raw,
            raw_for_scope,
            slice_raw,
            pick_months=pick_months,
            n_recent=n_recent,
            layout=layout if isinstance(layout, dict) else None,
        )
        cache_gen = int(st.session_state.get("workbook_cache_gen") or 0)
        gl_sheet_editor.render_gl_table_section(
            client,
            dict(st.secrets),
            slice_raw=slice_raw,
            layout=layout if isinstance(layout, dict) else None,
            gl_sheet_name=gl_sheet_name,
            object_path=object_path,
            include_tr=has_tr,
            cache_gen=cache_gen,
            scope_sig=gl_scope_sig,
            is_admin=is_admin,
            default_posting_date=gl_sheet_editor.default_posting_date_for_gl_scope(
                slice_raw,
                pick_months=pick_months,
                fp_lookup=fp_lookup,
                fiscal_start_month=fy_m,
            ),
        )

        with st.expander(tr("Raw sheet rows"), expanded=False):
            import gl_editor as gled

            raw_display = gled.normalize_gl_records_for_display(slice_raw)
            st.dataframe(pd.DataFrame(raw_display), width="stretch", hide_index=True)

        st.divider()
        try:
            gl_payload, gl_fname = _fin_gl_export_xlsx(
                bucket,
                object_path,
                gl_sheet_name,
                wcg,
            )
            st.download_button(
                tr("Download GL"),
                data=gl_payload,
                file_name=str(gl_fname),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="fin_gl_download_btn",
                help=tr(
                    "Pulls the master workbook from Supabase Storage and downloads a single-sheet .xlsx copy of the GL tab."
                ),
                width="stretch",
            )
        except Exception as e:
            st.error(str(e))

    if not isinstance(df_all, pd.DataFrame) or df_all.empty:
        with tab_bs, tab_is, tab_tb:
            st.info(tr("No analytics rows for this workbook."))
        return

    view_mode = str(st.session_state.get("dashboard_currency_view") or "Original Currency")
    use_usd = view_mode.startswith("USD") or "Reporting" in view_mode
    currencies = sorted(df_all["currency_iso"].dropna().astype(str).str.upper().unique().tolist())
    sel_ccy = st.multiselect(
        tr("Currencies"),
        options=currencies,
        default=currencies,
        key="fin_tabs_ccy",
    )
    df_ccy = df_all if not sel_ccy else df_all[df_all["currency_iso"].astype(str).str.upper().isin([x.upper() for x in sel_ccy])]
    df_ccy_tb = df_ccy
    if set_p:
        df_ccy = fkpi.filter_gl_by_fiscal_periods(df_ccy, set_p)

    if use_usd:
        debit_col, credit_col = "debit_usd", "credit_usd"
    else:
        debit_col, credit_col = "debit", "credit"

    try:
        bucket_doc = db.fetch_account_buckets_json(client)
    except Exception:
        import account_buckets as ab

        bucket_doc = ab.default_buckets_document()

    cat = gla.category_financial_totals(
        df_ccy,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
    )
    bs_groups = gla.balance_sheet_account_groups(
        df_ccy,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
    )
    is_groups = gla.income_statement_account_groups(
        df_ccy,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
    )
    fy_m = int(db.fetch_fiscal_start_month(client)) if isinstance(df_all, pd.DataFrame) and not df_all.empty else 1
    tb_df = gla.trial_balance(
        df_ccy_tb,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
        fiscal_periods=set_p if set_p else None,
        fiscal_start_month=fy_m,
    )
    unk_tb_df = gla.trial_balance_unknown_breakdown(
        df_ccy_tb,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
        fiscal_periods=set_p if set_p else None,
        fiscal_start_month=fy_m,
    )

    anchor_doc: dict[str, Any] = {}
    try:
        raw_anchor = db.fetch_balance_sheet_anchor_json(client)
        if isinstance(raw_anchor, dict):
            anchor_doc = raw_anchor
    except Exception:
        anchor_doc = {}
    re_blk = anchor_doc.get("retained_earnings")
    re_sheet = str((re_blk or {}).get("sheet") or "").strip() if isinstance(re_blk, dict) else ""
    re_cell_raw = str((re_blk or {}).get("cell_a1") or "").strip() if isinstance(re_blk, dict) else ""
    re_cell = re_cell_raw.upper().replace("$", "")

    bs_groups_for_stmt: dict[str, pd.DataFrame] = bs_groups
    retained_err: str | None = None
    retained_amt: float | None = None
    re_gl_roll: float = 0.0

    wcg_fin = int(st.session_state.get("workbook_cache_gen") or 0)
    if re_sheet and re_cell and str(object_path or "").strip():
        retained_amt, retained_err = _financials_cached_retained_earnings_cell(
            client,
            dict(st.secrets),
            cache_gen=wcg_fin,
            bucket=bucket,
            object_path=object_path,
            sheet_name=re_sheet,
            cell_a1=re_cell,
        )
    if retained_amt is not None:
        eq_full = bs_groups.get("Equity")
        if not isinstance(eq_full, pd.DataFrame):
            eq_full = pd.DataFrame()
        eq_other, eq_ret = gla.equity_rows_partition_retained(eq_full)
        re_gl_roll = gla.sum_equity_tb_bs_amount(eq_ret)
        bs_groups_for_stmt = {**bs_groups, "Equity": eq_other}

    ao_mx = pd.to_datetime(df_ccy["gl_date"], errors="coerce").max()
    fin_as_of = ao_mx.date().isoformat() if pd.notna(ao_mx) else ""
    fin_as_of_lbl = tr(f"As of {fin_as_of}") if fin_as_of else None
    currency_note = (str(st.session_state.get("dashboard_currency_view") or "").strip() or None)
    if pick_months:
        is_period_lbl = tr("For ") + ", ".join(pick_months)
    else:
        is_period_lbl = fin_as_of_lbl or tr("Activity in selected filters and currencies")

    period_net_bs = float(cat["total_revenue"]) - float(cat["total_expenses"])

    with tab_bs:
        k1, k2, k3 = st.columns(3)
        pref = "$" if use_usd else ""
        with k1:
            st.metric(tr("Assets"), f"{pref}{cat['assets_net']:,.2f}")
        with k2:
            st.metric(tr("Liabilities"), f"{pref}{cat['liabilities_net']:,.2f}")
        with k3:
            eq_part = bs_groups_for_stmt.get("Equity")
            if not isinstance(eq_part, pd.DataFrame):
                eq_part = pd.DataFrame()
            eq_show = gla.sum_equity_tb_bs_amount(eq_part)
            if retained_amt is not None:
                eq_show += float(retained_amt)
            if abs(period_net_bs) > 1e-9:
                eq_show += period_net_bs
            st.metric(tr("Equity"), f"{pref}{eq_show:,.2f}")
        if fin_as_of_lbl:
            st.caption(fin_as_of_lbl)
        if currency_note:
            st.caption(tr(currency_note))
        st.caption(
            tr(
                "Each line is the **net** balance for the filtered GL (liabilities: credit − debit); "
                "the ledger lists gross postings per entry, so a payable can show **0.00** when debits equal credits in-range. "
                "**Settings → Account buckets:** longer «contains» phrases are applied before short ones, and expense buckets "
                "never match captions that include **payable**, so **Legal fees payable** and **A/P** stay liabilities when the "
                "ledger has a balance unless you map them explicitly."
            )
        )
        if re_sheet and re_cell and str(object_path or "").strip():
            if retained_amt is not None:
                tol_re = max(0.01, abs(float(retained_amt)) * 1e-9)
                dv = abs(float(retained_amt) - float(re_gl_roll))
                if dv <= tol_re:
                    st.success(
                        tr(
                            "Retained earnings: workbook cell matches GL accounts whose names include "
                            f"«retained» and «earnings» (difference {pref}{dv:,.2f})."
                        )
                    )
                else:
                    st.warning(
                        tr(
                            "Retained earnings variance: workbook cell is "
                            f"{pref}{float(retained_amt):,.2f} but those GL lines sum to "
                            f"{pref}{float(re_gl_roll):,.2f} (difference {pref}{dv:,.2f})."
                        )
                    )
            elif retained_err:
                st.warning(tr(f"Could not read retained earnings from the workbook: {retained_err}"))
        bs_html, bs_h = stm_exp.balance_sheet_streamlit_html(
            bs_groups_for_stmt,
            title="Balance Sheet",
            as_of=fin_as_of_lbl,
            retained_earnings_excel_amount=retained_amt,
            period_net_income_for_equity=period_net_bs,
        )
        st.iframe(bs_html, height=min(bs_h, 900))
        try:
            bs_bytes = stm_exp.balance_sheet_formatted_xlsx_bytes(
                bs_groups_for_stmt,
                title="Balance Sheet",
                as_of=fin_as_of_lbl,
                retained_earnings_excel_amount=retained_amt,
                period_net_income_for_equity=period_net_bs,
            )
            st.download_button(
                tr("Download balance sheet (Excel)"),
                data=bs_bytes,
                file_name="balance_sheet.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="fin_dl_balance_sheet_fmt",
            )
        except Exception as e:
            st.error(str(e))

        exp_unk_title = tr("**Unclassified (Unknown)** — excluded from Assets / Liabilities / Equity totals above.")
        if unk_tb_df.empty:
            with st.expander(exp_unk_title, expanded=False):
                st.caption(tr("Nothing classifies as Unknown for this slice."))
        else:
            ud = float(pd.to_numeric(unk_tb_df["debits"], errors="coerce").fillna(0).sum())
            uc = float(pd.to_numeric(unk_tb_df["credits"], errors="coerce").fillna(0).sum())
            unb = float(pd.to_numeric(unk_tb_df["net_balance"], errors="coerce").fillna(0).sum())
            with st.expander(exp_unk_title, expanded=False):
                st.caption(
                    tr(
                        "These trial-balance lines use the same filters and currency columns as the statement. "
                        "Map them under **Settings → Account buckets** (or rename accounts) so they roll into the right section."
                    )
                )
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric(tr("Unknown — total debits"), f"{pref}{ud:,.2f}")
                with c2:
                    st.metric(tr("Unknown — total credits"), f"{pref}{uc:,.2f}")
                with c3:
                    st.metric(tr("Unknown — Σ net (debit − credit)"), f"{pref}{unb:,.2f}")
                show_unk = unk_tb_df.copy()
                for col in ("debits", "credits", "net_balance"):
                    if col in show_unk.columns:
                        show_unk[col] = pd.to_numeric(show_unk[col], errors="coerce").fillna(0.0)
                st.dataframe(
                    show_unk,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "account": st.column_config.TextColumn(tr("Account")),
                        "debits": st.column_config.NumberColumn(tr("Debits"), format="%.2f"),
                        "credits": st.column_config.NumberColumn(tr("Credits"), format="%.2f"),
                        "net_balance": st.column_config.NumberColumn(tr("Net (Dr − Cr)"), format="%.2f"),
                    },
                )

    with tab_is:
        m1, m2, m3 = st.columns(3)
        pref = "$" if use_usd else ""
        with m1:
            st.metric(tr("Total income"), f"{pref}{cat['total_revenue']:,.2f}")
        with m2:
            st.metric(tr("Total spending"), f"{pref}{cat['total_expenses']:,.2f}")
        with m3:
            net_pl = float(cat["total_revenue"]) - float(cat["total_expenses"])
            m3_lbl = tr("Net loss") if net_pl < -1e-9 else tr("Net income")
            st.metric(m3_lbl, f"{pref}{net_pl:,.2f}")
        st.caption(is_period_lbl)
        if currency_note:
            st.caption(tr(currency_note))
        is_html, is_h = stm_exp.income_statement_streamlit_html(
            is_groups,
            title="Income Statement",
            period_label=is_period_lbl,
            total_revenue=float(cat["total_revenue"]),
            total_expenses=float(cat["total_expenses"]),
        )
        st.iframe(is_html, height=min(is_h, 900))
        try:
            is_bytes = stm_exp.income_statement_formatted_xlsx_bytes(
                is_groups,
                title="Income Statement",
                period_label=is_period_lbl,
                total_revenue=float(cat["total_revenue"]),
                total_expenses=float(cat["total_expenses"]),
            )
            st.download_button(
                tr("Download income statement (Excel)"),
                data=is_bytes,
                file_name="income_statement.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="fin_dl_income_statement_fmt",
            )
        except Exception as e:
            st.error(str(e))

    with tab_tb:
        if tb_df.empty:
            st.info(tr("No rows."))
        else:
            tb_display = gla.trial_balance_for_display(tb_df, bucket_doc=bucket_doc)
            tb_title = "Trial Balance"
            try:
                org_id = st.session_state.get("org_id")
                if org_id:
                    org_row = org.fetch_organization(client, org_id)
                    if org_row and org_row.get("name"):
                        tb_title = str(org_row["name"])
            except Exception:
                pass
            tb_html, tb_h = stm_exp.trial_balance_streamlit_html(
                tb_display, title=tb_title, as_of=fin_as_of_lbl
            )
            st.iframe(tb_html, height=min(tb_h, 900))
            try:
                tb_bytes = stm_exp.trial_balance_formatted_xlsx_bytes(
                    tb_display, title=tb_title, as_of=fin_as_of_lbl
                )
                st.download_button(
                    tr("Download trial balance (Excel)"),
                    data=tb_bytes,
                    file_name="trial_balance.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="fin_dl_trial_balance_fmt",
                )
            except Exception as e:
                st.error(str(e))


def render(client) -> None:
    role = str(st.session_state.get("role") or "")
    st.header(tr("Financials"))
    _render_financial_workbook_tabs(client, role=role)
