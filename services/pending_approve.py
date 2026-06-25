"""Approve pending transactions — write to Excel workbook in Supabase Storage."""

from __future__ import annotations

import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from supabase import Client

import database as db
import excel_engine as xleng
import gl_workbook_loader as gl_wb
import org
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


def approve_pending_transaction(
    client: Client,
    row: dict[str, Any],
    *,
    secrets: dict[str, Any],
) -> None:
    pid = str(row["id"])
    uid = db.get_current_user_id(client)
    path_secret = str(secrets.get("MASTER_WORKBOOK_STORAGE_PATH") or "").strip()
    object_path = db.resolve_master_workbook_file_id(client, path_secret)
    if not object_path.strip():
        raise ValueError(
            "Upload an Excel workbook in Settings, or set MASTER_WORKBOOK_STORAGE_PATH in secrets."
        )

    bucket = sbw.master_workbook_bucket(secrets)
    tmp_path = None
    try:
        tmp_path = sbw.download_master_to_tempfile(client, bucket, object_path)
        if not xleng.path_supports_gl_append(tmp_path):
            fn = Path(object_path).name or "linked file"
            raise ValueError(
                f"Can't write to «{fn}». Link an Excel .xlsx or .xlsm file. "
                "CSV and older Excel work for viewing only — upload a modern Excel file in Settings."
            )

        pdate = date.fromisoformat(str(row["posting_date"]))
        post_ccy = str(row.get("currency_iso") or "USD").strip().upper()[:3]
        if len(post_ccy) != 3:
            post_ccy = "USD"
        post_tr = xleng.coerce_gl_transaction_number(row.get("gl_transaction_no"))

        jl = row.get("journal_lines")
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
                description=row["description"],
                lines=lines,
                sheet_name=db.resolve_gl_sheet_name(client),
                layout=db.fetch_gl_layout_json(client) or None,
                currency_iso=post_ccy,
                transaction_number=post_tr,
            )
        else:
            amount = Decimal(str(row["amount"]))
            xleng.append_double_entry(
                tmp_path,
                gl_date=pdate,
                description=row["description"],
                debit_account=row["debit_account"],
                credit_account=row["credit_account"],
                amount=amount,
                sheet_name=db.resolve_gl_sheet_name(client),
                layout=db.fetch_gl_layout_json(client) or None,
                currency_iso=post_ccy,
                transaction_number=post_tr,
            )

        sbw.upload_master_file(client, bucket, object_path, tmp_path)
        gl_wb.refresh_workbook_session_cache(client, secrets)
        db.update_pending_status(
            client,
            pid,
            status="approved",
            reviewed_by=uid,
            clear_last_error=True,
        )
        try:
            email = db.get_current_user_email(client)
        except Exception:
            email = None
        org.log_audit_event(
            client,
            action="entry.approved",
            details={
                "pending_id": pid,
                "description": str(row.get("description") or "")[:200],
                "currency_iso": post_ccy,
                "approver_email": email,
                "approver_user_id": uid,
            },
        )
    except Exception as exc:
        msg = str(exc)
        try:
            db.set_pending_error(client, pid, msg)
        except Exception:
            pass
        raise
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
