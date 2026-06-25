"""Build and persist GL sheet edit plans (master workbook in Supabase Storage)."""

from __future__ import annotations

from typing import Any, Mapping, Optional

import pandas as pd

import database as db
import excel_engine as xleng
import gl_workbook_loader as gl_wb
import supabase_storage_workbook as sbw


def records_to_editor_frame(
    records: list[dict[str, Any]],
    *,
    include_tr: bool = True,
) -> pd.DataFrame:
    """Editable grid rows keyed by ``_excel_row`` (workbook line number)."""
    rows: list[dict[str, Any]] = []
    for r in records:
        er = r.get("_excel_row")
        if not isinstance(er, int) or er < 1:
            continue
        row: dict[str, Any] = {
            "_excel_row": int(er),
            "Date": str(r.get("gl_date") or "")[:32],
            "Account": str(r.get("account") or ""),
            "Debit": float(r.get("debit") or 0),
            "Credit": float(r.get("credit") or 0),
            "Details": str(r.get("description") or ""),
        }
        if include_tr:
            tr = r.get("transaction_number")
            row["Tr"] = "" if tr is None else str(tr).strip()
        rows.append(row)
    if not rows:
        return pd.DataFrame(
            columns=["_excel_row", "Date", "Account", "Debit", "Credit", "Details"]
            + (["Tr"] if include_tr else [])
        )
    return pd.DataFrame(rows)


def _norm_float(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _norm_str(v: Any) -> str:
    return str(v or "").strip()


def plan_from_editor_diff(
    baseline: pd.DataFrame,
    edited: pd.DataFrame,
    *,
    include_tr: bool = True,
) -> xleng.GlEditPlan:
    """
    Compare grid state to the loaded slice and produce a :class:`~excel_engine.GlEditPlan`.

    New rows have ``_excel_row`` zero or missing; removed rows become deletes.
    """
    base_by_er: dict[int, dict[str, Any]] = {}
    if not baseline.empty and "_excel_row" in baseline.columns:
        for rec in baseline.to_dict(orient="records"):
            try:
                er = int(rec.get("_excel_row") or 0)
            except (TypeError, ValueError):
                continue
            if er > 0:
                base_by_er[er] = rec

    seen: set[int] = set()
    updates: list[dict[str, Any]] = []
    inserts: list[dict[str, Any]] = []

    cols = ["Date", "Account", "Debit", "Credit", "Details"] + (["Tr"] if include_tr else [])

    for rec in edited.to_dict(orient="records"):
        try:
            er = int(rec.get("_excel_row") or 0)
        except (TypeError, ValueError):
            er = 0

        fields: dict[str, Any] = {
            "gl_date": _norm_str(rec.get("Date")),
            "account": _norm_str(rec.get("Account")),
            "description": _norm_str(rec.get("Details")),
            "debit": _norm_float(rec.get("Debit")),
            "credit": _norm_float(rec.get("Credit")),
        }
        if include_tr:
            fields["transaction_number"] = _norm_str(rec.get("Tr")) or None

        if er <= 0:
            inserts.append(fields)
            continue

        seen.add(er)
        orig = base_by_er.get(er)
        if orig is None:
            inserts.append(fields)
            continue

        patch: dict[str, Any] = {"excel_row": er}
        changed = False
        if _norm_str(orig.get("Date")) != fields["gl_date"]:
            patch["gl_date"] = fields["gl_date"]
            changed = True
        if _norm_str(orig.get("Account")) != fields["account"]:
            patch["account"] = fields["account"]
            changed = True
        if _norm_str(orig.get("Details")) != fields["description"]:
            patch["description"] = fields["description"]
            changed = True
        if abs(_norm_float(orig.get("Debit")) - fields["debit"]) > 1e-9:
            patch["debit"] = fields["debit"]
            changed = True
        if abs(_norm_float(orig.get("Credit")) - fields["credit"]) > 1e-9:
            patch["credit"] = fields["credit"]
            changed = True
        if include_tr:
            otr = _norm_str(orig.get("Tr")) or None
            ntr = fields.get("transaction_number")
            if otr != ntr:
                patch["transaction_number"] = ntr
                changed = True
        if changed:
            updates.append(patch)

    deletes = sorted(er for er in base_by_er if er not in seen)
    return xleng.GlEditPlan(
        updates=updates,
        delete_rows=deletes,
        insert_rows=inserts,
        swap_rows=[],
    )


def persist_gl_edit_plan(
    client: Any,
    secrets: Mapping[str, Any],
    plan: xleng.GlEditPlan,
    *,
    sheet_name: str,
    layout: dict[str, Any] | None,
) -> Optional[str]:
    """Download master workbook, apply plan, upload, refresh session GL cache. Returns error text."""
    path_secret = str(secrets.get("MASTER_WORKBOOK_STORAGE_PATH") or "").strip()
    object_path = db.resolve_master_workbook_file_id(client, path_secret)
    if not object_path.strip():
        return "No workbook linked. Add one in **Settings**."
    bucket = sbw.master_workbook_bucket(secrets)
    tmp_path = None
    try:
        tmp_path = sbw.download_master_to_tempfile(client, bucket, object_path)
        xleng.apply_gl_edit_plan(
            tmp_path,
            plan,
            sheet_name=sheet_name,
            layout=layout or None,
        )
        sbw.upload_master_file(client, bucket, object_path, tmp_path)
        gl_wb.refresh_workbook_session_cache(client, dict(secrets))
        return None
    except Exception as e:
        return str(e)
    finally:
        if tmp_path:
            import os

            if os.path.isfile(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


def persist_row_swap(
    client: Any,
    secrets: Mapping[str, Any],
    row_a: int,
    row_b: int,
    *,
    sheet_name: str,
    layout: dict[str, Any] | None,
) -> Optional[str]:
    plan = xleng.GlEditPlan(updates=[], delete_rows=[], insert_rows=[], swap_rows=[(row_a, row_b)])
    return persist_gl_edit_plan(client, secrets, plan, sheet_name=sheet_name, layout=layout)
