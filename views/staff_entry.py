"""Staff: enter transactions and submit to pending queue."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
import streamlit as st

import currency_iso4217 as ccy
import database as db
import invoice_extract as invx
import gl_workbook_loader as gl_wb

_MAX_LINES = 16


def _line_keys(i: int) -> tuple[str, str, str]:
    return (f"staff_j_{i}_a", f"staff_j_{i}_d", f"staff_j_{i}_c")


def _clear_line_widgets(n_max: int) -> None:
    for i in range(n_max):
        for k in _line_keys(i):
            st.session_state.pop(k, None)


def _clear_invoice_session() -> None:
    for k in (
        "_inv_ext",
        "_inv_bytes",
        "_inv_name",
        "_staff_extract_banner",
    ):
        st.session_state.pop(k, None)


def _display_pending_row(r: dict) -> dict:
    """Flatten journal_lines into readable columns for the recent-submissions grid."""
    out = {k: v for k, v in r.items() if k != "journal_lines"}
    jl = r.get("journal_lines")
    if jl:
        if isinstance(jl, str):
            try:
                jl = json.loads(jl)
            except json.JSONDecodeError:
                jl = None
        if isinstance(jl, list) and jl:
            try:
                td = sum(Decimal(str(x.get("debit") or "0")) for x in jl)
            except (InvalidOperation, TypeError, KeyError):
                td = Decimal("0")
            out["amount"] = format(td.quantize(Decimal("0.01")), "f")
            out["debit_account"] = "(multiple)"
            out["credit_account"] = f"{len(jl)} lines"
    if r.get("invoice_original_filename"):
        out["invoice_file"] = r["invoice_original_filename"]
    return out


def _prefill_from_extraction(client, ext: dict[str, Any]) -> None:
    desc = invx.build_description_from_extraction(ext)
    if desc:
        st.session_state.desc_field = desc
    pd_dt = invx.posting_date_from_extraction(ext)
    if pd_dt:
        st.session_state.staff_posting_date = pd_dt
    cg = ext.get("currency_guess")
    if cg and str(cg).strip().upper()[:3] in ccy.ACTIVE_ISO4217:
        st.session_state.staff_entry_ccy = str(cg).strip().upper()[:3]

    draft = invx.draft_journal_lines_from_extraction(ext)
    draft = invx.apply_account_rule_hints(client, draft, ext)
    n = max(2, min(_MAX_LINES, len(draft)))
    st.session_state.staff_j_line_count = n
    _clear_line_widgets(_MAX_LINES)
    for i, ln in enumerate(draft):
        if i >= _MAX_LINES:
            break
        ka, kd, kc = _line_keys(i)
        st.session_state[ka] = str(ln.get("account") or "")
        st.session_state[kd] = str(ln.get("debit") or "")
        st.session_state[kc] = str(ln.get("credit") or "")


def render(client) -> None:
    st.session_state["_app_page_marker"] = "staff_entry"

    _FORM_CLEAR_FLAG = "_staff_pending_form_clear"

    msg = st.session_state.pop("_staff_success_msg", None)
    if msg:
        st.success(msg)

    banner = st.session_state.pop("_staff_extract_banner", None)
    if banner == "success":
        st.success("Filled the form from the file — review amounts and accounts.")
    elif banner == "weak":
        st.warning(
            "Nothing usable was pulled from this file (common for photos without OCR). "
            "Install **Tesseract**, add **pytesseract** / **Pillow**, set **TESSERACT_CMD** if needed, "
            "or use a text PDF — then enter amounts manually if it still fails."
        )

    if st.session_state.pop(_FORM_CLEAR_FLAG, False):
        _clear_line_widgets(_MAX_LINES)
        st.session_state.pop("desc_field", None)
        st.session_state.pop("staff_gl_tr_manual", None)
        st.session_state.pop("_staff_peek_tr", None)
        st.session_state.staff_j_line_count = 2
        _clear_invoice_session()

    if "staff_j_line_count" not in st.session_state:
        st.session_state.staff_j_line_count = 2

    if "staff_posting_date" not in st.session_state:
        st.session_state.staff_posting_date = date.today()

    if "staff_entry_ccy" not in st.session_state:
        st.session_state.staff_entry_ccy = db.fetch_display_currency_iso(client)

    nlines = int(st.session_state.staff_j_line_count)
    if nlines < 2:
        st.session_state.staff_j_line_count = 2
        nlines = 2

    st.header("Entries & invoices")

    with st.container(border=True):
        st.markdown("### Start from an invoice file")
        st.caption(
            "Pick PDF or image, click **Extract from invoice**. We fill description, dates, currency, "
            "and amounts; **you choose accounts** and check debits = credits. Then submit — "
            "your invoice travels with the request for admins."
        )
        inv_upl = st.file_uploader(
            "Invoice file",
            type=["pdf", "png", "jpg", "jpeg", "webp"],
            key="staff_invoice_upload",
            help="PDF with selectable text works best. JPG/PNG need Tesseract OCR installed.",
        )
        ex1, ex2 = st.columns([1, 1])
        with ex1:
            extract_go = st.button("Extract from invoice", type="primary")
        with ex2:
            if st.button("Clear invoice draft"):
                _clear_invoice_session()
                st.rerun()

        if extract_go:
            if not inv_upl:
                st.warning("Choose an invoice file first.")
            else:
                try:
                    try:
                        tess_secret = st.secrets.get("TESSERACT_CMD")
                    except Exception:
                        tess_secret = None
                    invx.configure_tesseract_cmd(str(tess_secret).strip() if tess_secret else None)
                    raw = inv_upl.getvalue()
                    ext = invx.extract_invoice(raw, inv_upl.name)
                    st.session_state["_inv_ext"] = ext
                    st.session_state["_inv_bytes"] = raw
                    st.session_state["_inv_name"] = inv_upl.name
                    _prefill_from_extraction(client, ext)
                    if invx.extraction_has_usable_amounts(ext):
                        st.session_state["_staff_extract_banner"] = "success"
                    else:
                        st.session_state["_staff_extract_banner"] = "weak"
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        ext_cur = st.session_state.get("_inv_ext")
        if ext_cur and isinstance(ext_cur, dict):
            warns = ext_cur.get("warnings") or []
            if warns:
                ocr_kw = ("tesseract", "pytesseract", "pillow", "ocr")
                for w in warns:
                    txt = str(w)
                    wl = txt.lower()
                    if any(k in wl for k in ocr_kw):
                        st.warning(txt)
                    else:
                        st.caption(f"Note: {txt}")

    st.subheader("Transaction details")
    st.caption(
        "Describe the entry, adjust posting date and currency if needed, then edit lines below. "
        "You can skip the invoice section and enter everything manually."
    )

    description = st.text_area("What this is for", key="desc_field", height=88)
    if description.strip():
        sug = db.suggest_accounts_from_description(client, description, limit=5)
        if sug:
            st.markdown("**Quick picks** (fills your first debit row and first credit row)")
            for i, r in enumerate(sug):
                lbl = f"{r['keyword']}: **{r['debit_account']}** / **{r['credit_account']}**"
                if st.button(lbl, key=f"sug_btn_{i}"):
                    st.session_state[_line_keys(0)[0]] = r["debit_account"]
                    st.session_state[_line_keys(1)[0]] = r["credit_account"]
                    st.rerun()

    txn_ccy = st.selectbox(
        "Currency for this entry",
        options=list(ccy.ACTIVE_ISO4217),
        key="staff_entry_ccy",
        help="How amounts look when they are written into Excel.",
    )

    posting = st.date_input("Posting date", key="staff_posting_date")

    peek = st.session_state.get("_staff_peek_tr")
    if peek is None:
        with st.spinner("Reading suggested transaction number from workbook…"):
            peek = gl_wb.peek_next_transaction_number(client, dict(st.secrets))
        st.session_state["_staff_peek_tr"] = peek
    sug, has_tr, perr = peek
    tr_refresh_peek, _ = st.columns([1, 4])
    with tr_refresh_peek:
        if st.button("Refresh Tr. No.", help="Re-read the linked workbook for the next transaction number"):
            st.session_state.pop("_staff_peek_tr", None)
            st.rerun()
    if perr:
        st.caption(f"Could not read transaction numbers from workbook: {perr}")
    elif not has_tr:
        st.caption(
            "This workbook layout has no transaction-number column; numbering is skipped when posting."
        )
    else:
        st.caption(f"Next ledger transaction number if you leave the override blank: **{sug}**")

    manual_gl_tr = st.text_input(
        "Transaction number (optional override)",
        key="staff_gl_tr_manual",
        placeholder="Leave blank — uses next number from workbook when posted",
        help="Leave empty so Excel gets the automatic next number. Enter a value to force that Tr. No. when an admin posts.",
    )

    st.subheader("Line items")
    for i in range(nlines):
        ka, kd, kc = _line_keys(i)
        st.markdown(f"**Line {i + 1}**")
        lc1, lc2, lc3 = st.columns([2.6, 1, 1])
        with lc1:
            st.text_input("Account", key=ka, placeholder="e.g. 6200‑utilities")
        with lc2:
            st.text_input("Debit", key=kd, placeholder="0.00")
        with lc3:
            st.text_input("Credit", key=kc, placeholder="0.00")

    b1, b2, sp, b3 = st.columns([1, 1, 2, 1])
    with b1:
        if st.button("＋ Line", disabled=nlines >= _MAX_LINES):
            st.session_state.staff_j_line_count = nlines + 1
            st.rerun()
    with b2:
        if st.button("－ Last line", disabled=nlines <= 2):
            li = nlines - 1
            for k in _line_keys(li):
                st.session_state.pop(k, None)
            st.session_state.staff_j_line_count = nlines - 1
            st.rerun()

    def _gather_lines() -> list[dict[str, str]]:
        raw_lines: list[dict[str, str]] = []
        for i in range(nlines):
            ka, kd, kc = _line_keys(i)
            acct = str(st.session_state.get(ka) or "").strip()
            debit_s = str(st.session_state.get(kd) or "").strip()
            credit_s = str(st.session_state.get(kc) or "").strip()
            if not acct and not debit_s and not credit_s:
                continue
            raw_lines.append({"account": acct, "debit": debit_s or "0", "credit": credit_s or "0"})
        return raw_lines

    if st.button("Submit for approval", type="primary"):
        if not description.strip():
            st.error("Enter a description")
            return
        lines_raw = _gather_lines()
        if len(lines_raw) < 2:
            st.error("Add at least two rows with an account and an amount.")
            return
        inv_bytes = st.session_state.get("_inv_bytes")
        inv_name = st.session_state.get("_inv_name")
        ext_save = st.session_state.get("_inv_ext")
        try:
            tr_kw: dict[str, Any] = {}
            mt = str(manual_gl_tr or "").strip()
            if mt:
                tr_kw["gl_transaction_no"] = mt
            row = db.insert_pending_transaction(
                client,
                description=description.strip(),
                posting_date=posting,
                currency_iso=str(txn_ccy),
                journal_lines=lines_raw,
                invoice_extraction_json=ext_save if isinstance(ext_save, dict) else None,
                **tr_kw,
            )
            if inv_bytes and inv_name:
                bucket = sbd.documents_bucket(st.secrets)
                safe_nm = sbd.safe_document_filename(str(inv_name))
                object_path = f"invoices/{row['id']}/{safe_nm}"
                sbd.upload_document_bytes(
                    client,
                    bucket,
                    object_path,
                    inv_bytes,
                    filename_hint=safe_nm,
                )
                db.update_pending_invoice_attachment(
                    client,
                    row["id"],
                    object_path=object_path,
                    original_filename=str(inv_name),
                )
            st.session_state["_staff_success_msg"] = f"Sent for approval (`{row['id'][:8]}…`)"
            st.session_state[_FORM_CLEAR_FLAG] = True
            st.rerun()
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.subheader("My recent requests")
    rows = db.list_my_pending(client)
    pending_only = [r for r in rows if r.get("status") == "pending"]
    if not pending_only:
        st.info("Nothing waiting right now.")
        return

    pref = [
        "description",
        "amount",
        "currency_iso",
        "gl_transaction_no",
        "debit_account",
        "credit_account",
        "invoice_file",
        "posting_date",
        "created_at",
    ]
    flat = [_display_pending_row(r) for r in pending_only]
    df = pd.DataFrame(flat)
    cols = [c for c in pref if c in df.columns]
    extra = [c for c in df.columns if c not in cols]
    st.dataframe(df[cols + extra], width="stretch", hide_index=True)
