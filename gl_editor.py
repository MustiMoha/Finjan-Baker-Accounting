"""Build and persist GL sheet edit plans (master workbook in Supabase Storage)."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional

import pandas as pd

import database as db
import excel_engine as xleng
import gl_workbook_loader as gl_wb
import supabase_storage_workbook as sbw

_MAX_BLOCK_SCAN_ROWS = 24


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
            "After row": 0,
            "Date": format_gl_date_for_editor(r.get("gl_date")),
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
            columns=["_excel_row", "After row", "Date", "Account", "Debit", "Credit", "Details"]
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


def format_gl_date_for_editor(val: Any) -> str:
    """Calendar date only (``YYYY-MM-DD``) for grid cells and edit plans — never a time component."""
    parsed = xleng.parse_gl_cell_to_date(val)
    if parsed is not None:
        return parsed.isoformat()
    s = _norm_str(val)
    if not s:
        return ""
    parsed2 = xleng.parse_gl_cell_to_date(s)
    if parsed2 is not None:
        return parsed2.isoformat()
    if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-":
        return s[:10]
    return s


def posting_date_for_editor_anchor(
    records: list[dict[str, Any]],
    anchor_er: int,
    *,
    default: date,
    include_tr: bool = True,
) -> date:
    """
    Posting date for **Add GL entry**: same calendar date as the chosen anchor row.

    Blank dates on continuation legs inherit the nearest prior dated line in workbook order.
    """
    anchor_er = int(anchor_er)
    pool = [
        dict(r)
        for r in records
        if _editor_row_int(r, "_excel_row") > 0
    ]
    if not pool:
        return default
    pool.sort(key=lambda r: _editor_row_int(r, "_excel_row"))
    idx = -1
    for i, rec in enumerate(pool):
        if _editor_row_int(rec, "_excel_row") == anchor_er:
            idx = i
            break
    if idx < 0:
        return default
    for j in range(idx, -1, -1):
        ds = format_gl_date_for_editor(pool[j].get("Date") or pool[j].get("gl_date"))
        if ds:
            gd = xleng.parse_gl_cell_to_date(ds)
            if gd is not None:
                return gd
    block_end = resolve_insert_after_excel_row(
        records, anchor_er, include_tr=include_tr, workbook_records=None
    )
    for rec in pool:
        if _editor_row_int(rec, "_excel_row") == block_end:
            ds = format_gl_date_for_editor(rec.get("Date") or rec.get("gl_date"))
            if ds:
                gd = xleng.parse_gl_cell_to_date(ds)
                if gd is not None:
                    return gd
    return default


def validate_editor_posting_rows_have_accounts(
    records: list[dict[str, Any]],
) -> str | None:
    """Return an error when a grid line has amounts but a blank Account (pre-save check)."""
    missing: list[int] = []
    for rec in records:
        deb = _norm_float(rec.get("Debit") if "Debit" in rec else rec.get("debit"))
        cred = _norm_float(rec.get("Credit") if "Credit" in rec else rec.get("credit"))
        if deb <= 1e-9 and cred <= 1e-9:
            continue
        acct = _norm_str(rec.get("Account") or rec.get("account"))
        if not acct:
            after = _editor_row_int(rec, "After row")
            er = _editor_row_int(rec, "_excel_row")
            missing.append(er if er > 0 else after)
    if not missing:
        return None
    shown = ", ".join(str(x) for x in sorted({m for m in missing if m > 0})[:8])
    return (
        f"Line(s) near row {shown or 'new entry'} have debit/credit but no account name. "
        "Enter **Account** on each leg before saving."
    )


def validate_gl_editor_display_order(
    records: list[dict[str, Any]],
    *,
    workbook_records: list[dict[str, Any]] | None = None,
) -> str | None:
    """
    Return an error message when grid row order does not match workbook sequence + insert anchors.

    Call before **Add to grid** / **Save changes**; pair with :func:`canonicalize_editor_display_order`
    in the UI layer to repair shuffled pending lines.
    """
    if not records:
        return None

    workbook_ers = [
        _editor_row_int(r, "_excel_row")
        for r in records
        if _editor_row_int(r, "_excel_row") > 0
    ]
    prev = 0
    for er in workbook_ers:
        if er <= prev:
            return (
                f"Workbook rows are out of order (row {er} appears after row {prev}). "
                "Discard new lines or refresh the GL view, then try again."
            )
        prev = er

    if workbook_records:
        full_seq = sorted(
            _editor_row_int(r, "_excel_row")
            for r in workbook_records
            if _editor_row_int(r, "_excel_row") > 0
        )
        full_set = set(full_seq)
        editor_set = set(workbook_ers)
        expected = [er for er in full_seq if er in editor_set]
        if workbook_ers != expected:
            return (
                "The visible GL slice is not in the same order as the master workbook. "
                "Refresh Financials or discard edits, then add lines again."
            )

    anchor_idx_by_er = {
        _editor_row_int(rec, "_excel_row"): i
        for i, rec in enumerate(records)
        if _editor_row_int(rec, "_excel_row") > 0
    }
    for i, rec in enumerate(records):
        if _editor_row_int(rec, "_excel_row") > 0:
            continue
        after = _editor_row_int(rec, "After row")
        if after <= 0:
            return "New lines are missing an insert anchor. Discard them and add the entry again."
        anchor_idx = anchor_idx_by_er.get(after)
        if anchor_idx is None:
            return (
                f"New lines reference row {after}, which is not in this grid. "
                "Refresh or pick another anchor."
            )
        block_start = anchor_idx + 1
        block_end = block_start
        while block_end < len(records) and _editor_row_int(records[block_end], "_excel_row") <= 0:
            if _editor_row_int(records[block_end], "After row") != after:
                break
            block_end += 1
        if not (block_start <= i < block_end):
            return (
                f"New lines are not grouped directly below row {after}. "
                "Discard new lines or refresh, then add the entry again."
            )
    return None


def _editor_row_int(rec: dict[str, Any], key: str) -> int:
    try:
        return int(rec.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _pool_row_tr(rec: dict[str, Any], *, include_tr: bool) -> str:
    if not include_tr:
        return ""
    raw = rec.get("Tr")
    if raw is None and "transaction_number" in rec:
        raw = rec.get("transaction_number")
    return _norm_str(raw)


def _pool_row_date(rec: dict[str, Any]) -> str:
    return format_gl_date_for_editor(rec.get("Date") or rec.get("gl_date"))


def _pool_row_debit(rec: dict[str, Any]) -> float:
    if "Debit" in rec:
        return _norm_float(rec.get("Debit"))
    return _norm_float(rec.get("debit"))


def _pool_row_credit(rec: dict[str, Any]) -> float:
    if "Credit" in rec:
        return _norm_float(rec.get("Credit"))
    return _norm_float(rec.get("credit"))


def _pool_rows_for_partition(
    pool: list[dict[str, Any]],
    *,
    include_tr: bool,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rec in pool:
        er = _editor_row_int(rec, "_excel_row")
        if er <= 0:
            continue
        tr = _pool_row_tr(rec, include_tr=include_tr)
        out.append(
            {
                "_excel_row": er,
                "transaction_number": tr or None,
            }
        )
    return out


def _resolve_block_end_by_partition(
    pool: list[dict[str, Any]],
    anchor_er: int,
    *,
    include_tr: bool,
) -> int | None:
    part_rows = _pool_rows_for_partition(pool, include_tr=include_tr)
    if not any(r.get("transaction_number") for r in part_rows):
        return None
    for block in xleng.partition_journal_blocks(part_rows):
        ers = [int(b["_excel_row"]) for b in block]
        if anchor_er in ers:
            return max(ers)
    return None


def _resolve_block_end_local_scan(
    pool: list[dict[str, Any]],
    anchor_er: int,
    *,
    include_tr: bool,
) -> int:
    ordered = sorted(
        [dict(r) for r in pool if _editor_row_int(r, "_excel_row") > 0],
        key=lambda r: _editor_row_int(r, "_excel_row"),
    )
    idx = -1
    for i, rec in enumerate(ordered):
        if _editor_row_int(rec, "_excel_row") == anchor_er:
            idx = i
            break
    if idx < 0:
        return anchor_er

    block_end = idx
    starter_tr = _pool_row_tr(ordered[idx], include_tr=include_tr)
    entry_date = _pool_row_date(ordered[idx])
    prev_er = anchor_er
    for j in range(idx + 1, min(len(ordered), idx + 1 + _MAX_BLOCK_SCAN_ROWS)):
        rec = ordered[j]
        er = _editor_row_int(rec, "_excel_row")
        if er > prev_er + 8:
            break
        tr = _pool_row_tr(rec, include_tr=include_tr)
        if tr:
            if starter_tr and tr != starter_tr:
                break
            if not starter_tr:
                break
        explicit_date = _norm_str(rec.get("Date") or rec.get("gl_date"))
        if explicit_date and entry_date and explicit_date[:10] != entry_date[:10]:
            deb_n = _pool_row_debit(rec)
            cred_n = _pool_row_credit(rec)
            if deb_n > 1e-9:
                break
            if cred_n > 1e-9 and (not starter_tr or (tr and tr != starter_tr)):
                break
        deb = _pool_row_debit(rec)
        cred = _pool_row_credit(rec)
        prev_cred = _pool_row_credit(ordered[block_end])
        if deb > 1e-9 and cred <= 1e-9 and prev_cred > 1e-9:
            if explicit_date and entry_date and explicit_date[:10] == entry_date[:10]:
                pass
            else:
                break
        if deb > 1e-9 or cred > 1e-9:
            block_end = j
            prev_er = er
        else:
            break
    return _editor_row_int(ordered[block_end], "_excel_row")


def _journal_block_end_on_pool(
    pool: list[dict[str, Any]],
    anchor_er: int,
    *,
    include_tr: bool,
) -> int:
    hit = _resolve_block_end_by_partition(pool, anchor_er, include_tr=include_tr)
    if hit is not None:
        return int(hit)
    return _resolve_block_end_local_scan(pool, anchor_er, include_tr=include_tr)


def normalize_pending_insert_anchors(
    records: list[dict[str, Any]],
    *,
    include_tr: bool = True,
    workbook_records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Resolve each pending line's ``After row`` to the bottom of its journal block."""
    if not any(_editor_row_int(r, "_excel_row") <= 0 for r in records):
        return list(records)
    out: list[dict[str, Any]] = []
    for rec in records:
        row = dict(rec)
        if _editor_row_int(row, "_excel_row") > 0:
            out.append(row)
            continue
        after = _editor_row_int(row, "After row")
        if after > 0:
            row["After row"] = resolve_insert_after_excel_row(
                records,
                after,
                include_tr=include_tr,
                workbook_records=workbook_records,
            )
        out.append(row)
    return out


def resolve_insert_after_excel_row(
    records: list[dict[str, Any]],
    anchor_er: int,
    *,
    include_tr: bool = True,
    workbook_records: list[dict[str, Any]] | None = None,
) -> int:
    """
    Bottom workbook row of the journal block containing ``anchor_er``.

    Block bounds come from the **editor slice** (what the user sees). The full workbook
    cache only fills in missing continuation legs (e.g. credit row omitted from the slice)
    and never extends past the next workbook row already visible in that slice.
    """
    anchor_er = int(anchor_er)
    end = _journal_block_end_on_pool(records, anchor_er, include_tr=include_tr)

    editor_ers = sorted(
        _editor_row_int(r, "_excel_row")
        for r in records
        if _editor_row_int(r, "_excel_row") > 0
    )
    next_entry_er = min((e for e in editor_ers if e > end), default=None)

    if workbook_records:
        wb_end = _journal_block_end_on_pool(
            workbook_records, anchor_er, include_tr=include_tr
        )
        cap = int(wb_end)
        if next_entry_er is not None:
            cap = min(cap, next_entry_er - 1)
        return max(end, min(int(wb_end), cap))

    return end


def format_transaction_number_display(value: Any) -> str:
    """String form for UI/Arrow (avoids mixed int/str in ``transaction_number`` columns)."""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    if isinstance(value, bool):
        return ""
    return str(value).strip()


def normalize_gl_records_for_display(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coerce ``transaction_number`` to str so Streamlit/PyArrow can render GL rows."""
    out: list[dict[str, Any]] = []
    for rec in records:
        row = dict(rec)
        if "transaction_number" in row:
            tr = row.get("transaction_number")
            row["transaction_number"] = (
                None
                if tr is None or format_transaction_number_display(tr) == ""
                else format_transaction_number_display(tr)
            )
        out.append(row)
    return out


def normalize_editor_dataframe_dtypes(df: pd.DataFrame, *, include_tr: bool = True) -> pd.DataFrame:
    """Force text/number columns to Arrow-safe dtypes before ``st.data_editor``."""
    if df.empty:
        return df
    out = df.copy()
    if "_excel_row" in out.columns:
        out["_excel_row"] = out["_excel_row"].fillna(0).astype(int)
    if "After row" in out.columns:
        out["After row"] = out["After row"].fillna(0).astype(int)
    if "row_num" in out.columns:
        out["row_num"] = out["row_num"].fillna(0).astype(int)
    for col in ("Date", "Account", "Details"):
        if col in out.columns:
            if col == "Date":
                out[col] = out[col].map(format_gl_date_for_editor)
            else:
                out[col] = out[col].fillna("").astype(str)
    for col in ("Debit", "Credit"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    if include_tr and "Tr" in out.columns:
        out["Tr"] = out["Tr"].map(format_transaction_number_display)
    return out


def _text_field_changed_for_plan(orig_val: Any, new_val: Any) -> bool:
    """True when a text field edit should be persisted (ignore blank widget glitches)."""
    orig_s = _norm_str(orig_val)
    new_s = _norm_str(new_val)
    if orig_s == new_s:
        return False
    if not new_s and orig_s:
        return False
    return True


def plan_from_editor_diff(
    baseline: pd.DataFrame,
    edited: pd.DataFrame,
    *,
    include_tr: bool = True,
    delete_scope: set[int] | None = None,
    infer_deletes: bool = True,
    workbook_records: list[dict[str, Any]] | None = None,
) -> xleng.GlEditPlan:
    """
    Compare grid state to the loaded slice and produce a :class:`~excel_engine.GlEditPlan`.

    ``delete_scope``: when set, only workbook rows in this set may be inferred as deletes.
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

    edited_recs = edited.to_dict(orient="records")
    wb_pool = workbook_records if workbook_records is not None else edited_recs
    prev_er = 0
    for rec in edited_recs:
        er_raw = rec.get("_excel_row")
        if er_raw is None or (isinstance(er_raw, float) and pd.isna(er_raw)):
            er = 0
        else:
            try:
                er = int(er_raw)
            except (TypeError, ValueError):
                er = 0

        fields: dict[str, Any] = {
            "gl_date": format_gl_date_for_editor(rec.get("Date")),
            "account": _norm_str(rec.get("Account")),
            "description": _norm_str(rec.get("Details")),
            "debit": _norm_float(rec.get("Debit")),
            "credit": _norm_float(rec.get("Credit")),
        }
        if include_tr:
            fields["transaction_number"] = _norm_str(rec.get("Tr")) or None

        if er <= 0:
            try:
                after = int(rec.get("After row") or 0)
            except (TypeError, ValueError):
                after = 0
            if after <= 0 and prev_er > 0:
                after = prev_er
            if after > 0:
                after = resolve_insert_after_excel_row(
                    edited_recs,
                    after,
                    include_tr=include_tr,
                    workbook_records=workbook_records,
                )
                fields["insert_after"] = after
                fields["insert_below_exact"] = True
            inserts.append(fields)
            prev_er = after if after > 0 else prev_er
            continue

        seen.add(er)
        prev_er = er
        orig = base_by_er.get(er)
        if orig is None:
            try:
                after = int(rec.get("After row") or 0)
            except (TypeError, ValueError):
                after = 0
            if after <= 0 and prev_er > 0:
                after = prev_er
            if after > 0:
                after = resolve_insert_after_excel_row(
                    edited_recs,
                    after,
                    include_tr=include_tr,
                    workbook_records=workbook_records,
                )
                fields["insert_after"] = after
                fields["insert_below_exact"] = True
            inserts.append(fields)
            continue

        patch: dict[str, Any] = {"excel_row": er}
        changed = False
        if _text_field_changed_for_plan(orig.get("Date"), fields["gl_date"]):
            patch["gl_date"] = fields["gl_date"]
            changed = True
        if _text_field_changed_for_plan(orig.get("Account"), fields["account"]):
            patch["account"] = fields["account"]
            changed = True
        if _text_field_changed_for_plan(orig.get("Details"), fields["description"]):
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
            if _text_field_changed_for_plan(otr, ntr or ""):
                patch["transaction_number"] = ntr
                changed = True
        if changed:
            updates.append(patch)

    scope = delete_scope if delete_scope is not None else set(base_by_er)
    if infer_deletes:
        deletes = sorted(er for er in base_by_er if er not in seen and er in scope)
    else:
        deletes = []
    return xleng.GlEditPlan(
        updates=updates,
        delete_rows=deletes,
        insert_rows=inserts,
        swap_rows=[],
    )


def persist_gl_row_deletes(
    client: Any,
    secrets: Mapping[str, Any],
    delete_targets: list[dict[str, Any]],
    *,
    sheet_name: str,
    layout: dict[str, Any] | None,
) -> Optional[str]:
    """Faux-delete multiple GL lines in one save (clear cells; sheet row count unchanged)."""
    checks: list[dict[str, Any]] = []
    for spec in delete_targets:
        try:
            er = int(spec.get("excel_row") or 0)
        except (TypeError, ValueError):
            continue
        if er < 1:
            continue
        checks.append(
            {
                "excel_row": er,
                "account": _norm_str(spec.get("account")),
                "debit": float(spec.get("debit") or 0),
                "credit": float(spec.get("credit") or 0),
            }
        )
    rows = sorted({int(c["excel_row"]) for c in checks})
    if not rows:
        return "No workbook rows selected."
    plan = xleng.GlEditPlan(
        updates=[],
        delete_rows=rows,
        insert_rows=[],
        swap_rows=[],
        delete_row_checks=checks,
    )
    prior_raw: list[dict[str, Any]] | None = None
    try:
        import streamlit as st

        cached = st.session_state.get("master_gl_rows_raw")
        if isinstance(cached, list):
            prior_raw = list(cached)
    except Exception:
        prior_raw = None
    return persist_gl_edit_plan(
        client,
        secrets,
        plan,
        sheet_name=sheet_name,
        layout=layout,
        faux_preserve_prior=prior_raw,
        faux_deleted_excel_rows=set(rows),
    )


def persist_gl_edit_plan(
    client: Any,
    secrets: Mapping[str, Any],
    plan: xleng.GlEditPlan,
    *,
    sheet_name: str,
    layout: dict[str, Any] | None,
    faux_preserve_prior: list[dict[str, Any]] | None = None,
    faux_deleted_excel_rows: set[int] | list[int] | None = None,
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
        preserve_prior = faux_preserve_prior if plan.delete_rows else None
        preserve_deleted = faux_deleted_excel_rows if plan.delete_rows else None
        gl_wb.refresh_workbook_session_cache(
            client,
            dict(secrets),
            faux_preserve_prior=preserve_prior,
            faux_deleted_excel_rows=preserve_deleted,
        )
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


def persist_single_gl_row_delete(
    client: Any,
    secrets: Mapping[str, Any],
    excel_row: int,
    *,
    sheet_name: str,
    layout: dict[str, Any] | None,
) -> Optional[str]:
    """Clear exactly one workbook GL line (never batched with grid edits)."""
    return persist_gl_row_deletes(
        client,
        secrets,
        [
            {
                "excel_row": int(excel_row),
                "account": "",
                "debit": 0.0,
                "credit": 0.0,
            }
        ],
        sheet_name=sheet_name,
        layout=layout,
    )


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


def blank_editor_row(
    *,
    insert_after: int = 0,
    include_tr: bool = True,
    pending_id: int = 0,
) -> dict[str, Any]:
    """One empty grid line for the GL editor (``pending_id`` <= 0 until saved to the workbook)."""
    row: dict[str, Any] = {
        "_excel_row": int(pending_id),
        "After row": int(insert_after),
        "Date": "",
        "Account": "",
        "Debit": 0.0,
        "Credit": 0.0,
        "Details": "",
    }
    if include_tr:
        row["Tr"] = ""
    return row
