"""Admin: approve or reject pending transactions; on approve, write to Excel and Supabase Storage."""

from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import streamlit as st

import database as db
import excel_engine as xleng
import gl_workbook_loader as gl_wb
import supabase_storage_documents as sbd
import supabase_storage_workbook as sbw


def _journal_lines_as_tuples(rows: list[dict]) -> list[tuple[str, Decimal, Decimal]]:
    out: list[tuple[str, Decimal, Decimal]] = []
    for i, x in enumerate(rows):
        acct = str(x.get("account") or "").strip()
        if not acct:
            raise ValueError(f"Journal line {i + 1} is missing «account»")
        out.append(
            (
                acct,
                Decimal(str(x.get("debit") or "0")),
                Decimal(str(x.get("credit") or "0")),
            )
        )
    return out


def render(client) -> None:
    st.session_state["_app_page_marker"] = "approvals"
    st.header("Approvals")
    rows = db.list_pending_transactions(client, status="pending")
    if not rows:
        st.info("No transactions waiting.")
        return

    path_secret = str(st.secrets.get("MASTER_WORKBOOK_STORAGE_PATH") or "").strip()
    object_path = db.resolve_master_workbook_file_id(client, path_secret)

    for r in rows:
        pid = r["id"]
        jl = r.get("journal_lines")
        if isinstance(jl, str):
            try:
                jl = json.loads(jl)
            except json.JSONDecodeError:
                jl = None
        kind = f"{len(jl)} lines" if isinstance(jl, list) and jl else "simple entry"
        head = (r.get("description") or "")[:56]
        with st.expander(f"{head} — {kind} — {pid[:8]}"):
            gtno = r.get("gl_transaction_no")
            if gtno:
                st.caption(f"Transaction number override: **{gtno}**")
            if isinstance(jl, list) and jl:
                st.markdown("**Several lines**")
                st.dataframe(jl, width="stretch", hide_index=True)
            else:
                st.json(
                    {
                        "description": r["description"],
                        "amount": r["amount"],
                        "currency_iso": r.get("currency_iso"),
                        "gl_transaction_no": r.get("gl_transaction_no"),
                        "debit": r.get("debit_account"),
                        "credit": r.get("credit_account"),
                        "posting_date": r["posting_date"],
                        "created_at": r["created_at"],
                    }
                )

            inv_path = r.get("invoice_object_path")
            inv_name = r.get("invoice_original_filename")
            if inv_path:
                try:
                    bucket = sbd.documents_bucket(st.secrets)
                    url = sbd.create_document_signed_url(client, bucket, str(inv_path), expires_in=2700)
                    st.markdown(f"**Invoice file:** [{inv_name or 'Download'}]({url})")
                except Exception as e:
                    st.warning(f"Invoice linked but URL failed: {e}")
            ext = r.get("invoice_extraction_json")
            if ext:
                with st.expander("Extracted invoice fields", expanded=False):
                    st.json(ext)

            c1, c2 = st.columns(2)
            with c1:
                if st.button("Reject", key=f"rej_{pid}"):
                    try:
                        uid = db.get_current_user_id(client)
                        db.update_pending_status(client, pid, status="rejected", reviewed_by=uid, clear_last_error=True)
                        st.success("Rejected.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with c2:
                if st.button("Approve & post", type="primary", key=f"app_{pid}"):
                    if not object_path.strip():
                        st.error(
                            "Upload an Excel workbook in **Settings**, or set **MASTER_WORKBOOK_STORAGE_PATH** in secrets."
                        )
                    else:
                        _approve_one(client, r, object_path)


def _approve_one(client, r: dict, object_path: str) -> None:
    pid = r["id"]
    uid = db.get_current_user_id(client)
    bucket = sbw.master_workbook_bucket(st.secrets)
    tmp_path = None
    try:
        tmp_path = sbw.download_master_to_tempfile(client, bucket, object_path)
        if not xleng.path_supports_gl_append(tmp_path):
            fn = Path(object_path).name or "linked file"
            raise ValueError(
                f"Can't write to «{fn}». Link an Excel **.xlsx** or **.xlsm** file. "
                "CSV and older Excel work for viewing only — upload a modern Excel file in Settings."
            )
        pdate = date.fromisoformat(str(r["posting_date"]))
        post_ccy = str(r.get("currency_iso") or "USD").strip().upper()[:3]
        if len(post_ccy) != 3:
            post_ccy = "USD"

        post_tr = xleng.coerce_gl_transaction_number(r.get("gl_transaction_no"))

        jl = r.get("journal_lines")
        if isinstance(jl, str):
            try:
                jl = json.loads(jl)
            except json.JSONDecodeError:
                jl = None

        if isinstance(jl, list) and len(jl) >= 2:
            lines = _journal_lines_as_tuples(jl)
            xleng.append_journal_entry(
                tmp_path,
                gl_date=pdate,
                description=r["description"],
                lines=lines,
                sheet_name=db.resolve_gl_sheet_name(client),
                layout=db.fetch_gl_layout_json(client) or None,
                currency_iso=post_ccy,
                transaction_number=post_tr,
            )
        else:
            amount = Decimal(str(r["amount"]))
            xleng.append_double_entry(
                tmp_path,
                gl_date=pdate,
                description=r["description"],
                debit_account=r["debit_account"],
                credit_account=r["credit_account"],
                amount=amount,
                sheet_name=db.resolve_gl_sheet_name(client),
                layout=db.fetch_gl_layout_json(client) or None,
                currency_iso=post_ccy,
                transaction_number=post_tr,
            )
        sbw.upload_master_file(client, bucket, object_path, tmp_path)
        gl_wb.refresh_workbook_session_cache(client, dict(st.secrets))

        db.update_pending_status(
            client,
            pid,
            status="approved",
            reviewed_by=uid,
            clear_last_error=True,
        )
        st.success("Posted to the workbook and saved online.")
        st.balloons()
        st.rerun()
    except Exception as e:
        msg = str(e)
        try:
            db.set_pending_error(client, pid, msg)
        except Exception:
            pass
        st.error(msg)
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
