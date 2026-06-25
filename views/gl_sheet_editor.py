"""GL tab: read-only view; admin edit mode behind **Edit GL**."""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

import database as db
import excel_engine as xleng
import fiscal
import gl_editor as gled
import gl_workbook_loader as gl_wb
from ui_locale import tr

_MAX_EDIT_ROWS = 250
_MAX_DELETE_BATCH = 100
_MAX_GL_ADD_LINES = 16
_GL_EDITOR_MAX_VISIBLE_ROWS = 14
_GL_EDITOR_ROW_PX = 36
_GL_EDITOR_HEADER_PX = 52
_AMOUNT_COLS = frozenset({"Debit", "Credit"})
_TEXT_COLS = ("Date", "Account", "Details", "Tr")


def _norm_editor_float(v: Any) -> float:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _editor_text_fields_unchanged(base: dict[str, Any], patch: dict[str, Any]) -> bool:
    for col in _TEXT_COLS:
        if str(base.get(col) or "").strip() != str(patch.get(col) or "").strip():
            return False
    return True


def _should_keep_baseline_text_field(
    base: dict[str, Any],
    patch: dict[str, Any],
    col: str,
) -> bool:
    """Keep Account/Details when Streamlit blanked text without a real user edit."""
    if col not in _TEXT_COLS:
        return False
    if str(patch.get(col) or "").strip():
        return False
    if not str(base.get(col) or "").strip():
        return False
    # Streamlit often blanks Account on credit legs; never drop a populated baseline account.
    if col == "Account":
        return True
    if _patch_wiped_all_posting_amounts(base, patch):
        return True
    # Credit-leg accounts often live one column right of particulars; the grid returns "".
    if col in ("Account", "Details"):
        for amount_col in _AMOUNT_COLS:
            if abs(_norm_editor_float(base.get(amount_col)) - _norm_editor_float(patch.get(amount_col))) > 1e-9:
                return False
        return True
    return False


def _patch_wiped_all_posting_amounts(base: dict[str, Any], patch: dict[str, Any]) -> bool:
    """Streamlit often zeroes both Debit and Credit while the user edits text fields."""
    patch_deb = _norm_editor_float(patch.get("Debit"))
    patch_cred = _norm_editor_float(patch.get("Credit"))
    base_deb = _norm_editor_float(base.get("Debit"))
    base_cred = _norm_editor_float(base.get("Credit"))
    return patch_deb == 0.0 and patch_cred == 0.0 and (
        abs(base_deb) > 1e-9 or abs(base_cred) > 1e-9
    )


def _should_keep_baseline_amount(
    base: dict[str, Any],
    patch: dict[str, Any],
    col: str,
) -> bool:
    """True when a NumberColumn came back as 0 but the user did not intentionally clear it."""
    if col not in _AMOUNT_COLS:
        return False
    pv = _norm_editor_float(patch.get(col))
    bv = _norm_editor_float(base.get(col))
    if abs(pv) > 1e-9 or abs(bv) <= 1e-9:
        return False
    if _patch_wiped_all_posting_amounts(base, patch):
        return True
    return _editor_text_fields_unchanged(base, patch)


def _merge_patch_into_row(
    base: dict[str, Any],
    patch: dict[str, Any],
    data_cols: list[str],
) -> dict[str, Any]:
    """
    Apply data_editor patch without clobbering Debit/Credit with widget zeros.

    Streamlit often returns 0 for NumberColumn cells even when the user only edited text.
    When patched amounts are zero but the baseline row had a posting, keep baseline amounts.
    """
    row = dict(base)

    for col in data_cols:
        if col == "_excel_row" or col not in patch:
            continue
        if _should_keep_baseline_amount(base, patch, col):
            continue
        if _excel_row_int(base.get("_excel_row")) > 0 and _should_keep_baseline_text_field(
            base, patch, col
        ):
            continue
        pv = patch[col]
        if col in _AMOUNT_COLS:
            if pv is None or (isinstance(pv, float) and pd.isna(pv)):
                continue
            if isinstance(pv, str) and not str(pv).strip():
                continue
        row[col] = pv
    return row


def _repair_pending_amounts(
    baseline: pd.DataFrame,
    pending: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop stale zero amounts / blank text from pending when the widget glitched."""
    base_by_er: dict[int, dict[str, Any]] = {}
    for rec in baseline.to_dict(orient="records"):
        er = _excel_row_int(rec.get("_excel_row"))
        if er > 0:
            base_by_er[er] = rec
    out: list[dict[str, Any]] = []
    for rec in pending:
        row = dict(rec)
        er = _excel_row_int(row.get("_excel_row"))
        b = base_by_er.get(er)
        if b is not None:
            glitch = rec
            for col in _AMOUNT_COLS:
                if _should_keep_baseline_amount(b, glitch, col):
                    row[col] = b[col]
            for col in _TEXT_COLS:
                if _should_keep_baseline_text_field(b, glitch, col):
                    row[col] = b[col]
        out.append(row)
    return out


def _grid_has_real_text_edits(base: pd.DataFrame, patch: pd.DataFrame) -> bool:
    """True when the user changed a text column (not only Streamlit amount glitches)."""
    b = base.reset_index(drop=True)
    p = patch.reset_index(drop=True)
    if len(p) != len(b):
        return True
    for i in range(len(b)):
        br = b.iloc[i].to_dict()
        pr = p.iloc[i].to_dict()
        for col in _TEXT_COLS:
            if col not in pr:
                continue
            if str(br.get(col) or "").strip() != str(pr.get(col) or "").strip():
                return True
    return False


def _infer_focus_display_row(base: pd.DataFrame, patch: pd.DataFrame) -> int | None:
    """Display index of the row the user most recently edited (for grid scroll restore)."""
    b = base.reset_index(drop=True)
    p = patch.reset_index(drop=True)
    if p.empty:
        return None
    if len(p) != len(b):
        return max(0, min(len(p) - 1, len(b)))
    cols = list(_TEXT_COLS) + list(_AMOUNT_COLS)
    for i in range(len(b) - 1, -1, -1):
        br = b.iloc[i].to_dict()
        pr = p.iloc[i].to_dict()
        for col in cols:
            if col not in pr or col not in br:
                continue
            if col in _AMOUNT_COLS:
                if abs(_norm_editor_float(br.get(col)) - _norm_editor_float(pr.get(col))) > 1e-9:
                    return i
            elif str(br.get(col) or "").strip() != str(pr.get(col) or "").strip():
                return i
    return None


def _suppress_on_change_key(scope_id: str) -> str:
    return f"fin_gl_suppress_on_change_{scope_id}"


def _widget_amounts_spuriously_zeroed(base_df: pd.DataFrame, widget_df: pd.DataFrame) -> bool:
    """Detect Streamlit data_editor session state that zeroed amounts without text edits."""
    if base_df.empty or widget_df.empty or "_excel_row" not in base_df.columns:
        return False
    if len(widget_df) != len(base_df):
        return False
    base_by_er: dict[int, dict[str, Any]] = {}
    for rec in base_df.to_dict(orient="records"):
        er = _excel_row_int(rec.get("_excel_row"))
        if er > 0:
            base_by_er[er] = rec
    for rec in widget_df.to_dict(orient="records"):
        er = _excel_row_int(rec.get("_excel_row"))
        b = base_by_er.get(er)
        if b is None:
            continue
        for col in _AMOUNT_COLS:
            if _should_keep_baseline_amount(b, rec, col):
                return True
    return False


def _sync_pending_amounts_after_delete(
    scope_id: str,
    deleted: set[int],
    *,
    include_tr: bool,
    baseline: pd.DataFrame | None = None,
) -> None:
    """
    After faux delete, set Debit/Credit on surviving pending rows from the reloaded workbook.

    Keeps text edits in pending; avoids Streamlit widget zeros overwriting real amounts.
    """
    key = _pending_edits_key(scope_id)
    raw = st.session_state.get(key)
    if not isinstance(raw, list) or not raw:
        return
    cached = st.session_state.get("master_gl_rows_raw")
    if not isinstance(cached, list):
        return
    fresh_by_er: dict[int, dict[str, Any]] = {}
    for rec in gled.records_to_editor_frame(cached, include_tr=include_tr).to_dict(orient="records"):
        er = _excel_row_int(rec.get("_excel_row"))
        if er > 0:
            fresh_by_er[er] = rec
    out: list[dict[str, Any]] = []
    for rec in raw:
        er = _excel_row_int(rec.get("_excel_row"))
        if er > 0 and er in deleted:
            continue
        row = dict(rec)
        if er > 0:
            fresh = fresh_by_er.get(er)
            if fresh is not None:
                row["Debit"] = fresh.get("Debit")
                row["Credit"] = fresh.get("Credit")
        out.append(row)
    if baseline is not None and not baseline.empty:
        out = _repair_pending_amounts(baseline, out)
    st.session_state[key] = out


def _rebuild_pending_after_delete(
    scope_id: str,
    post_delete_baseline: pd.DataFrame,
    deleted: set[int],
    *,
    include_tr: bool,
) -> pd.DataFrame:
    """
    Rebuild pending grid from refreshed baseline plus surviving edits and new lines.

    Prevents faux-deleted workbook rows from reappearing via partial pending overlay.
    """
    key = _pending_edits_key(scope_id)
    raw = st.session_state.get(key)
    if not isinstance(raw, list) or not raw:
        return _baseline_editor_df(baseline=post_delete_baseline)

    edits_by_er: dict[int, dict[str, Any]] = {}
    new_lines: list[dict[str, Any]] = []
    for rec in raw:
        er = _excel_row_int(rec.get("_excel_row"))
        if er in deleted:
            continue
        row = dict(rec)
        if er > 0:
            edits_by_er[er] = row
        else:
            new_lines.append(row)

    out: list[dict[str, Any]] = []
    for b in post_delete_baseline.to_dict(orient="records"):
        er = _excel_row_int(b.get("_excel_row"))
        out.append(edits_by_er.get(er, dict(b)))
    if new_lines:
        i = 0
        while i < len(new_lines):
            after = _excel_row_int(new_lines[i].get("After row"))
            block: list[dict[str, Any]] = []
            while i < len(new_lines) and _excel_row_int(new_lines[i].get("After row")) == after:
                block.append(new_lines[i])
                i += 1
            if after > 0 and block:
                out = _insert_compound_below_anchor(
                    out,
                    insert_after=after,
                    new_rows=block,
                    resolve_block_end=False,
                )
            else:
                out.extend(block)
    frame = pd.DataFrame(out).reset_index(drop=True)
    cached = st.session_state.get("master_gl_rows_raw")
    if isinstance(cached, list):
        fresh_by_er: dict[int, dict[str, Any]] = {}
        for rec in gled.records_to_editor_frame(cached, include_tr=include_tr).to_dict(
            orient="records"
        ):
            er = _excel_row_int(rec.get("_excel_row"))
            if er > 0:
                fresh_by_er[er] = rec
        repaired: list[dict[str, Any]] = []
        for rec in frame.to_dict(orient="records"):
            row = dict(rec)
            er = _excel_row_int(row.get("_excel_row"))
            if er > 0:
                fresh = fresh_by_er.get(er)
                if fresh is not None:
                    row["Debit"] = fresh.get("Debit")
                    row["Credit"] = fresh.get("Credit")
            repaired.append(row)
        frame = pd.DataFrame(_repair_pending_amounts(post_delete_baseline, repaired))
    st.session_state[key] = frame.to_dict(orient="records")
    return frame


def _reset_gl_editor_workspace_after_delete(
    cache_gen: int,
    scope_id: str,
    *,
    include_tr: bool,
    deleted: set[int],
    baseline: pd.DataFrame,
    rebuilt: pd.DataFrame | None = None,
) -> None:
    """Drop stale grid/session rows so the editor reloads from the refreshed workbook cache."""
    new_gen = int(st.session_state.get("workbook_cache_gen") or cache_gen)
    for gen in {int(cache_gen), new_gen}:
        st.session_state.pop(_local_edit_key(gen, scope_id), None)
        st.session_state.pop(_editor_widget_key(gen, scope_id), None)
        snap_key = _baseline_snap_key(gen, scope_id)
        st.session_state.pop(snap_key, None)
        st.session_state.pop(f"{snap_key}_fp", None)
        st.session_state.pop(_merged_snap_key(gen, scope_id), None)
    if rebuilt is not None:
        st.session_state[_pending_edits_key(scope_id)] = rebuilt.to_dict(orient="records")
        _persist_editor_df(cache_gen=new_gen, scope_id=scope_id, df=rebuilt)
        snap_key = _baseline_snap_key(new_gen, scope_id)
        st.session_state[snap_key] = _editable_baseline_df(baseline).to_dict(orient="records")
        st.session_state[f"{snap_key}_fp"] = _baseline_window_fingerprint(baseline)
    else:
        _sync_pending_amounts_after_delete(
            scope_id,
            deleted,
            include_tr=include_tr,
            baseline=baseline,
        )
    _bump_editor_widget_nonce(scope_id)


def default_posting_date_for_gl_scope(
    slice_raw: list[dict[str, Any]],
    *,
    pick_months: list[str],
    fp_lookup: dict[str, tuple[int, int]],
    fiscal_start_month: int,
) -> date:
    """
    First day of the latest calendar month in the Financials scope.

    Uses selected fiscal months when filtered; otherwise the latest ``gl_date`` in ``slice_raw``.
    """
    if pick_months and fp_lookup:
        tuples = [fp_lookup[m] for m in pick_months if m in fp_lookup]
        if tuples:
            fy, fp = max(tuples)
            y, m = fiscal.calendar_month_for_fiscal_period(fy, fp, fiscal_start_month)
            return date(y, m, 1)
    best: date | None = None
    for r in slice_raw:
        gd = xleng.parse_gl_cell_to_date(r.get("gl_date"))
        if gd is None:
            continue
        month_start = date(gd.year, gd.month, 1)
        if best is None or month_start > best:
            best = month_start
    return best if best is not None else date.today()


def _gl_editor_scroll_height(n_rows: int) -> int:
    """Fixed viewport height so long slices scroll inside the grid, not down the page."""
    cap = _GL_EDITOR_MAX_VISIBLE_ROWS * _GL_EDITOR_ROW_PX + _GL_EDITOR_HEADER_PX
    content = max(1, n_rows) * _GL_EDITOR_ROW_PX + _GL_EDITOR_HEADER_PX
    return min(cap, max(200, content))


def _gl_add_date_key(scope_id: str) -> str:
    return f"fin_gl_add_date_{scope_id}"


def _sync_gl_add_posting_date_to_anchor(
    scope_id: str,
    editor_df: pd.DataFrame,
    insert_after: int,
    fallback: date,
    *,
    include_tr: bool,
) -> None:
    """Default **Posting date** to the calendar date on the chosen anchor row."""
    key = _gl_add_date_key(scope_id)
    anchor_track = f"fin_gl_add_anchor_track_{scope_id}"
    picked = int(insert_after)
    if anchor_track not in st.session_state or int(st.session_state.get(anchor_track) or 0) != picked:
        st.session_state[key] = gled.posting_date_for_editor_anchor(
            editor_df.to_dict(orient="records"),
            picked,
            default=fallback,
            include_tr=include_tr,
        )
        st.session_state[anchor_track] = picked
    elif key not in st.session_state:
        st.session_state[key] = gled.posting_date_for_editor_anchor(
            editor_df.to_dict(orient="records"),
            picked,
            default=fallback,
            include_tr=include_tr,
        )


def _finalize_editor_records_or_error(
    records: list[dict[str, Any]],
    *,
    scope_id: str,
    include_tr: bool,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Canonicalize display order and verify the grid matches the master GL sequence."""
    canon = _canonicalize_editor_display_order(
        records, scope_id=scope_id, include_tr=include_tr
    )
    err = gled.validate_gl_editor_display_order(
        canon,
        workbook_records=_master_gl_workbook_records(),
    )
    if err:
        return None, err
    acct_err = gled.validate_editor_posting_rows_have_accounts(canon)
    if acct_err:
        return None, acct_err
    return canon, None


def _scope_id(scope_sig: str) -> str:
    sig = (scope_sig or "_all").strip()
    if len(sig) <= 48 and re.fullmatch(r"[\w|.,:-]+", sig):
        return sig.replace("|", "_")
    return hashlib.sha256(sig.encode()).hexdigest()[:12]


def _edit_mode_scope_key(scope_id: str) -> str:
    """Not tied to workbook cache_gen — survives refresh after each delete/save."""
    return f"fin_gl_edit_mode_{scope_id}"


def _local_edit_key(cache_gen: int, scope_id: str) -> str:
    return f"fin_gl_local_edit_{cache_gen}_{scope_id}"


def _editor_widget_nonce_key(scope_id: str) -> str:
    return f"fin_gl_ed_nonce_{scope_id}"


def _editor_widget_key(cache_gen: int, scope_id: str) -> str:
    nonce = int(st.session_state.get(_editor_widget_nonce_key(scope_id), 0) or 0)
    return f"fin_gl_ed_{cache_gen}_{scope_id}_{nonce}"


def _bump_editor_widget_nonce(scope_id: str) -> None:
    """Force a fresh ``st.data_editor`` after structural grid changes (e.g. add-entry form)."""
    nk = _editor_widget_nonce_key(scope_id)
    st.session_state[nk] = int(st.session_state.get(nk, 0) or 0) + 1


def _baseline_snap_key(cache_gen: int, scope_id: str) -> str:
    return f"fin_gl_baseline_{cache_gen}_{scope_id}"


def _merged_snap_key(cache_gen: int, scope_id: str) -> str:
    return f"fin_gl_merged_{cache_gen}_{scope_id}"


def _pending_edits_key(scope_id: str) -> str:
    """Unsaved grid edits; survives workbook cache_gen bumps and row delete."""
    return f"fin_gl_pending_{scope_id}"


def _faux_deleted_rows_key(scope_id: str) -> str:
    """Workbook rows cleared this edit session (must not be resurrected on Save)."""
    return f"fin_gl_faux_del_{scope_id}"


def _record_faux_deleted_rows(scope_id: str, excel_rows: set[int]) -> None:
    if not excel_rows:
        return
    key = _faux_deleted_rows_key(scope_id)
    prev = st.session_state.get(key)
    merged_set = set(prev) if isinstance(prev, (set, list, tuple)) else set()
    merged_set |= {int(x) for x in excel_rows if int(x) > 0}
    st.session_state[key] = sorted(merged_set)


def _faux_deleted_rows(scope_id: str) -> set[int]:
    raw = st.session_state.get(_faux_deleted_rows_key(scope_id))
    if not raw:
        return set()
    return {int(x) for x in raw if int(x) > 0}


def _clear_faux_deleted_rows(scope_id: str) -> None:
    st.session_state.pop(_faux_deleted_rows_key(scope_id), None)


def _scope_marker_key(cache_gen: int) -> str:
    return f"fin_gl_scope_{cache_gen}"


def _excel_row_int(v: Any) -> int:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _is_pending_insert_row(rec: dict[str, Any]) -> bool:
    """True for new lines not yet written to the workbook (``_excel_row`` <= 0)."""
    return _excel_row_int(rec.get("_excel_row")) <= 0


def _pending_row_id_key(scope_id: str) -> str:
    return f"fin_gl_pending_row_id_{scope_id}"


def _reset_pending_row_id_counter(scope_id: str) -> None:
    st.session_state.pop(_pending_row_id_key(scope_id), None)


def _next_pending_row_id(scope_id: str) -> int:
    """Stable negative ids for pending inserts (avoids Streamlit sorting Row # 0 to the top)."""
    key = _pending_row_id_key(scope_id)
    cur = int(st.session_state.get(key, 0) or 0)
    nxt = -1 if cur >= 0 else cur - 1
    st.session_state[key] = nxt
    return nxt


def _ensure_pending_row_ids(
    records: list[dict[str, Any]],
    scope_id: str,
) -> list[dict[str, Any]]:
    """Assign negative ``_excel_row`` ids to legacy pending lines stored as 0."""
    out: list[dict[str, Any]] = []
    for rec in records:
        row = dict(rec)
        if _is_pending_insert_row(row) and _excel_row_int(row.get("_excel_row")) == 0:
            row["_excel_row"] = _next_pending_row_id(scope_id)
        out.append(row)
    return out


def _apply_display_row_numbers(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Provisional **Row #** for the grid while editing.

    Workbook lines keep their true Excel row number; pending inserts show the slot
    after their anchor (e.g. 12, 13 below anchor 11). Full renumbering of every line
    happens only on **Save changes** via :func:`_project_coherent_row_numbers_on_save`.
    """
    pending_slots: dict[int, int] = {}
    out: list[dict[str, Any]] = []
    for rec in records:
        row = dict(rec)
        er = _excel_row_int(row.get("_excel_row"))
        if er > 0:
            row["row_num"] = er
        else:
            after = _excel_row_int(row.get("After row"))
            slot = pending_slots.get(after, 0)
            row["row_num"] = (after + 1 + slot) if after > 0 else 0
            pending_slots[after] = slot + 1
        out.append(row)
    return out


def _project_coherent_row_numbers_on_save(
    records: list[dict[str, Any]],
    *,
    faux_deleted: set[int],
) -> list[dict[str, Any]]:
    """
    Row # after this save: workbook lines shifted by pending inserts; pending lines numbered in place.

    Called only when building the save plan so deletes in the same session are respected.
    """
    pending_blocks: dict[int, list[dict[str, Any]]] = {}
    for rec in records:
        if not _is_pending_insert_row(rec):
            continue
        after = _excel_row_int(rec.get("After row"))
        pending_blocks.setdefault(after, []).append(dict(rec))

    insert_count_before: dict[int, int] = {}
    running = 0
    anchors = sorted(a for a in pending_blocks if a > 0)
    workbook_ers = sorted(
        {
            _excel_row_int(r.get("_excel_row"))
            for r in records
            if _excel_row_int(r.get("_excel_row")) > 0
            and _excel_row_int(r.get("_excel_row")) not in faux_deleted
        }
    )
    ai = 0
    for er in workbook_ers:
        while ai < len(anchors) and anchors[ai] < er:
            running += len(pending_blocks[anchors[ai]])
            ai += 1
        insert_count_before[er] = running

    block_index: dict[tuple[int, int], int] = {}
    for after, block in pending_blocks.items():
        for i, rec in enumerate(block):
            block_index[(after, _excel_row_int(rec.get("_excel_row")))] = i

    out: list[dict[str, Any]] = []
    for rec in records:
        row = dict(rec)
        er = _excel_row_int(row.get("_excel_row"))
        if er > 0:
            if er in faux_deleted:
                continue
            row["row_num"] = er + insert_count_before.get(er, 0)
        else:
            after = _excel_row_int(row.get("After row"))
            idx = block_index.get((after, er), 0)
            row["row_num"] = after + 1 + idx if after > 0 else 0
        out.append(row)
    return out


def _dataframe_for_grid_display(df: pd.DataFrame) -> pd.DataFrame:
    """Attach ``row_num`` for the visible Row # column (recomputed each render)."""
    if df.empty:
        out = df.copy()
        out["row_num"] = pd.Series(dtype=int)
        return out
    recs = _apply_display_row_numbers(df.to_dict(orient="records"))
    return pd.DataFrame(recs)


def _purge_scope_edit_workspace(scope_id: str) -> None:
    """Drop cached grid/snap/widget keys for this scope (all workbook cache generations)."""
    suffix = f"_{scope_id}"
    for key in list(st.session_state.keys()):
        if not isinstance(key, str) or not key.startswith("fin_gl_"):
            continue
        if key == _edit_mode_scope_key(scope_id):
            continue
        if key.endswith(suffix):
            st.session_state.pop(key, None)


def _reset_edit_workspace(cache_gen: int, scope_id: str, *, keep_edit_mode: bool = False) -> None:
    edit_on = bool(st.session_state.get(_edit_mode_scope_key(scope_id))) if keep_edit_mode else False
    st.session_state.pop(_local_edit_key(cache_gen, scope_id), None)
    st.session_state.pop(_editor_widget_key(cache_gen, scope_id), None)
    snap_key = _baseline_snap_key(cache_gen, scope_id)
    st.session_state.pop(snap_key, None)
    st.session_state.pop(f"{snap_key}_fp", None)
    st.session_state.pop(_merged_snap_key(cache_gen, scope_id), None)
    if keep_edit_mode and edit_on:
        st.session_state[_edit_mode_scope_key(scope_id)] = True
    else:
        st.session_state.pop(_edit_mode_scope_key(scope_id), None)


def _clear_pending_edits(scope_id: str) -> None:
    st.session_state.pop(_pending_edits_key(scope_id), None)


def _clear_scope_state(cache_gen: int, scope_id: str) -> None:
    _clear_pending_edits(scope_id)
    _clear_faux_deleted_rows(scope_id)
    _reset_pending_row_id_counter(scope_id)
    _reset_edit_workspace(cache_gen, scope_id, keep_edit_mode=False)


def clear_financials_gl_edit_session_state() -> None:
    """Drop all GL editor widget/snap keys (e.g. after Financials **Refresh**)."""
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith("fin_gl_"):
            st.session_state.pop(key, None)


def _ensure_scope(cache_gen: int, scope_id: str) -> None:
    marker = _scope_marker_key(cache_gen)
    prev = st.session_state.get(marker)
    if prev != scope_id:
        was_editing = isinstance(prev, str) and bool(
            st.session_state.get(_edit_mode_scope_key(prev))
        )
        if isinstance(prev, str):
            _clear_pending_edits(prev)
            _reset_edit_workspace(cache_gen, prev, keep_edit_mode=False)
        st.session_state[marker] = scope_id
        if was_editing:
            st.session_state[_edit_mode_scope_key(scope_id)] = True


def _merge_edited_with_after_row(orig: pd.DataFrame, edited: pd.DataFrame) -> pd.DataFrame:
    merged = edited.reset_index(drop=True).copy()
    orig_recs = orig.reset_index(drop=True).to_dict(orient="records")
    after_vals: list[int] = []
    prev_er = 0
    for i in range(len(merged)):
        er = _excel_row_int(merged.at[i, "_excel_row"])
        rec_ar = (
            _excel_row_int(merged.at[i, "After row"])
            if "After row" in merged.columns
            else 0
        )
        if er <= 0 and rec_ar > 0:
            ar = rec_ar
        elif er <= 0:
            ar = prev_er if prev_er > 0 else 0
        elif i < len(orig_recs) and "After row" in orig_recs[i]:
            ar = _excel_row_int(orig_recs[i].get("After row"))
        else:
            ar = 0
        after_vals.append(ar)
        if er > 0:
            prev_er = er
        elif ar > 0:
            prev_er = ar
    merged["After row"] = after_vals
    return merged


def _baseline_editor_df(*, baseline: pd.DataFrame) -> pd.DataFrame:
    if baseline.empty:
        return baseline.copy()
    return baseline.reset_index(drop=True).copy()


def _editable_baseline_df(baseline: pd.DataFrame) -> pd.DataFrame:
    """Match the row window shown in the GL editor (tail cap)."""
    df = _baseline_editor_df(baseline=baseline)
    if len(df) > _MAX_EDIT_ROWS:
        return df.tail(_MAX_EDIT_ROWS).reset_index(drop=True)
    return df


def _excel_rows_in_df(df: pd.DataFrame) -> set[int]:
    if df.empty or "_excel_row" not in df.columns:
        return set()
    out: set[int] = set()
    for rec in df.to_dict(orient="records"):
        er = _excel_row_int(rec.get("_excel_row"))
        if er > 0:
            out.add(er)
    return out


def _clamp_editor_to_baseline(editor_df: pd.DataFrame, baseline: pd.DataFrame) -> pd.DataFrame:
    """Keep only new lines and rows in the editable baseline window."""
    allowed = _excel_rows_in_df(baseline)
    kept: list[dict[str, Any]] = []
    for rec in editor_df.to_dict(orient="records"):
        er = _excel_row_int(rec.get("_excel_row"))
        if er <= 0 or er in allowed:
            kept.append(rec)
    if kept:
        return pd.DataFrame(kept).reset_index(drop=True)
    return _baseline_editor_df(baseline=baseline)


def _apply_pending_over_baseline(
    baseline: pd.DataFrame,
    pending: list[dict[str, Any]],
    *,
    scope_id: str = "",
) -> pd.DataFrame:
    """
    Rebuild the editor grid from stashed pending rows in **display order**.

    When ``pending`` is the full merged grid (every workbook row in the slice is present), use
    that order as-is so inserted lines (``_excel_row`` 0) stay below their anchor.

    When ``pending`` only patches some rows (e.g. after :func:`_prune_pending_to_baseline`),
    overlay those edits onto the baseline slice and keep other baseline rows unchanged.
    """
    if not pending:
        return _baseline_editor_df(baseline=baseline)

    base_df = _baseline_editor_df(baseline=baseline)
    allowed = _excel_rows_in_df(base_df)
    pending_ers = {
        _excel_row_int(r.get("_excel_row"))
        for r in pending
        if _excel_row_int(r.get("_excel_row")) > 0
    }
    if allowed.issubset(pending_ers):
        return pd.DataFrame(
            _canonicalize_editor_display_order(pending, scope_id=scope_id)
        ).reset_index(drop=True)

    pending_by_er = {
        _excel_row_int(r.get("_excel_row")): dict(r)
        for r in pending
        if _excel_row_int(r.get("_excel_row")) > 0
    }
    new_lines = [
        dict(r)
        for r in pending
        if _excel_row_int(r.get("_excel_row")) <= 0
    ]
    out: list[dict[str, Any]] = []
    for rec in base_df.to_dict(orient="records"):
        er = _excel_row_int(rec.get("_excel_row"))
        out.append(pending_by_er.get(er, rec))
    if new_lines:
        out = _merge_new_lines_into_records(out, new_lines)
    return pd.DataFrame(_canonicalize_editor_display_order(out, scope_id=scope_id)).reset_index(
        drop=True
    )


def _stash_pending_edits(
    scope_id: str,
    merged: pd.DataFrame,
    *,
    baseline: pd.DataFrame | None = None,
) -> None:
    records = _canonicalize_editor_display_order(merged.to_dict(orient="records"), scope_id=scope_id)
    if baseline is not None and not baseline.empty:
        records = _repair_pending_amounts(baseline, records)
        records = _canonicalize_editor_display_order(records, scope_id=scope_id)
    st.session_state[_pending_edits_key(scope_id)] = records


def _patch_from_editor_return(edited_return: pd.DataFrame) -> pd.DataFrame:
    """Same-run ``st.data_editor`` return — authoritative on Save and after Enter/blur."""
    return _strip_ui_columns(edited_return)


def _drop_pending_rows(scope_id: str, deleted: set[int]) -> None:
    key = _pending_edits_key(scope_id)
    raw = st.session_state.get(key)
    if not isinstance(raw, list):
        return
    st.session_state[key] = [
        r
        for r in raw
        if _excel_row_int(r.get("_excel_row")) <= 0
        or _excel_row_int(r.get("_excel_row")) not in deleted
    ]


def _prune_pending_to_baseline(scope_id: str, baseline: pd.DataFrame) -> None:
    """Keep pending edits only for rows still in the current GL slice (e.g. after delete)."""
    key = _pending_edits_key(scope_id)
    raw = st.session_state.get(key)
    if not isinstance(raw, list):
        return
    allowed = _excel_rows_in_df(_editable_baseline_df(baseline))
    st.session_state[key] = [
        r
        for r in raw
        if _excel_row_int(r.get("_excel_row")) <= 0
        or _excel_row_int(r.get("_excel_row")) in allowed
    ]


def _load_editor_df(
    *,
    cache_gen: int,
    scope_id: str,
    baseline: pd.DataFrame,
) -> pd.DataFrame:
    """Display order matches the period-filtered slice (no re-sort)."""
    pending = st.session_state.get(_pending_edits_key(scope_id))
    if isinstance(pending, list) and pending:
        pending = _repair_pending_amounts(baseline, pending)
        return _clamp_editor_to_baseline(
            _apply_pending_over_baseline(baseline, pending, scope_id=scope_id),
            baseline,
        )
    local = st.session_state.get(_local_edit_key(cache_gen, scope_id))
    if isinstance(local, list) and local:
        return _clamp_editor_to_baseline(pd.DataFrame(local), baseline)
    return _baseline_editor_df(baseline=baseline)


def _persist_editor_df(
    *,
    cache_gen: int,
    scope_id: str,
    df: pd.DataFrame,
) -> None:
    st.session_state[_local_edit_key(cache_gen, scope_id)] = df.to_dict(orient="records")


def _gl_add_line_count_key(scope_id: str) -> str:
    return f"fin_gl_add_nlines_{scope_id}"


def _gl_add_line_keys(scope_id: str, i: int) -> tuple[str, str, str]:
    return (f"fin_gl_add_{scope_id}_{i}_a", f"fin_gl_add_{scope_id}_{i}_d", f"fin_gl_add_{scope_id}_{i}_c")


def _anchor_options_from_editor(editor_df: pd.DataFrame) -> list[tuple[int, str]]:
    """Workbook row numbers eligible as insert anchors (existing lines only)."""
    opts: list[tuple[int, str]] = []
    for rec in editor_df.to_dict(orient="records"):
        er = _excel_row_int(rec.get("_excel_row"))
        if er <= 0:
            continue
        acct = str(rec.get("Account") or "").strip() or "—"
        if len(acct) > 48:
            acct = acct[:45] + "…"
        opts.append((er, f"Row {er} — {acct}"))
    return opts


def _master_gl_workbook_records() -> list[dict[str, Any]] | None:
    """Full parsed GL cache (unfiltered by fiscal month) for insert-anchor resolution."""
    cached = st.session_state.get("master_gl_rows_raw")
    if isinstance(cached, list) and cached:
        return list(cached)
    return None


def _resolve_insert_after_in_editor_records(
    records: list[dict[str, Any]],
    anchor_er: int,
    *,
    include_tr: bool = True,
) -> int:
    """Row number to insert below in the grid (bottom of the journal block)."""
    return gled.resolve_insert_after_excel_row(
        records,
        int(anchor_er),
        include_tr=include_tr,
        workbook_records=_master_gl_workbook_records(),
    )


def _canonicalize_editor_display_order(
    records: list[dict[str, Any]],
    *,
    include_tr: bool = True,
    scope_id: str = "",
) -> list[dict[str, Any]]:
    """
    Stable grid order: workbook rows by line number, pending inserts directly under their anchor.

    Pending lines use negative ``_excel_row`` ids; visible Row # comes from ``row_num``.
    """
    if scope_id:
        records = _ensure_pending_row_ids(records, scope_id)
    records = gled.normalize_pending_insert_anchors(
        records,
        include_tr=include_tr,
        workbook_records=_master_gl_workbook_records(),
    )
    existing = [dict(r) for r in records if _excel_row_int(r.get("_excel_row")) > 0]
    pending = [dict(r) for r in records if _is_pending_insert_row(r)]
    existing.sort(key=lambda r: _excel_row_int(r.get("_excel_row")))
    out = existing
    groups: dict[int, list[dict[str, Any]]] = {}
    for rec in pending:
        after = _excel_row_int(rec.get("After row"))
        groups.setdefault(after, []).append(rec)
    for after in sorted(groups.keys()):
        block = groups[after]
        if after > 0 and block:
            out = _insert_compound_below_anchor(
                out,
                insert_after=after,
                new_rows=block,
                include_tr=include_tr,
                resolve_block_end=False,
            )
        else:
            out.extend(block)
    return out


def _insert_compound_below_anchor(
    records: list[dict[str, Any]],
    *,
    insert_after: int,
    new_rows: list[dict[str, Any]],
    include_tr: bool = True,
    resolve_block_end: bool = True,
) -> list[dict[str, Any]]:
    """Insert pending lines in display order immediately below the anchor row."""
    if not new_rows:
        return list(records)
    anchor_er = int(insert_after)
    if resolve_block_end:
        resolved_after = _resolve_insert_after_in_editor_records(
            records, anchor_er, include_tr=include_tr
        )
    else:
        resolved_after = anchor_er
    patched_rows: list[dict[str, Any]] = []
    for nr in new_rows:
        row = dict(nr)
        row["After row"] = resolved_after
        patched_rows.append(row)
    out = list(records)
    insert_at = -1
    for i, rec in enumerate(out):
        if _excel_row_int(rec.get("_excel_row")) == resolved_after:
            insert_at = i
    if insert_at < 0:
        for i, rec in enumerate(out):
            er = _excel_row_int(rec.get("_excel_row"))
            if er > 0 and anchor_er <= er <= resolved_after:
                insert_at = i
    for i, rec in enumerate(out):
        if not _is_pending_insert_row(rec):
            continue
        ar = _excel_row_int(rec.get("After row"))
        if ar in (anchor_er, resolved_after):
            if insert_at < 0:
                insert_at = i
            else:
                insert_at = max(insert_at, i)
    if insert_at < 0:
        raise ValueError(
            f"Cannot place new lines below workbook row {resolved_after}: that row is not in the "
            "current GL view. Widen **Rows shown** on Financials, refresh the workbook, then add again."
        )
    for j, row in enumerate(patched_rows):
        out.insert(insert_at + 1 + j, row)
    return out


def _editor_rows_from_compound_entry(
    *,
    scope_id: str,
    insert_after: int,
    posting_date: date,
    details: str,
    journal_lines: list[dict[str, str]],
    include_tr: bool,
    transaction_number: str | None = None,
) -> list[dict[str, Any]]:
    date_s = gled.format_gl_date_for_editor(posting_date)
    tr_s = (transaction_number or "").strip()
    rows: list[dict[str, Any]] = []
    for i, ln in enumerate(journal_lines):
        row = gled.blank_editor_row(
            insert_after=insert_after,
            include_tr=include_tr,
            pending_id=_next_pending_row_id(scope_id),
        )
        row["Date"] = date_s if i == 0 else ""
        row["Account"] = ln["account"]
        row["Debit"] = float(ln["debit"])
        row["Credit"] = float(ln["credit"])
        row["Details"] = details if i == 0 else ""
        if include_tr and tr_s and i == 0:
            row["Tr"] = tr_s
        rows.append(row)
    return rows


def _first_new_row_display_index(records: list[dict[str, Any]], insert_after: int) -> int | None:
    for i, rec in enumerate(records):
        if not _is_pending_insert_row(rec):
            continue
        if _excel_row_int(rec.get("After row")) == insert_after:
            return i
    return None


def _gather_gl_add_lines(scope_id: str, nlines: int) -> list[dict[str, str]]:
    raw: list[dict[str, str]] = []
    for i in range(nlines):
        ka, kd, kc = _gl_add_line_keys(scope_id, i)
        acct = str(st.session_state.get(ka) or "").strip()
        debit_s = str(st.session_state.get(kd) or "").strip()
        credit_s = str(st.session_state.get(kc) or "").strip()
        if not acct and not debit_s and not credit_s:
            continue
        raw.append({"account": acct, "debit": debit_s or "0", "credit": credit_s or "0"})
    return raw


def _clear_gl_add_line_widgets(scope_id: str, n_max: int = _MAX_GL_ADD_LINES) -> None:
    for i in range(n_max):
        for k in _gl_add_line_keys(scope_id, i):
            st.session_state.pop(k, None)


def _try_add_compound_from_form(
    *,
    client: Any,
    secrets: dict[str, Any],
    scope_id: str,
    editor_df: pd.DataFrame,
    include_tr: bool,
    default_posting_date: date,
) -> tuple[pd.DataFrame | None, int | None]:
    """
    Render the add-entry form. On **Add to grid**, return merged records and display index of the first new line.
    """
    anchor_opts = _anchor_options_from_editor(editor_df)
    if not anchor_opts:
        with st.expander(tr("Add GL entry"), expanded=False):
            st.caption(tr("No workbook rows in this slice — widen **Rows shown** or refresh."))
        return None, None

    nkey = _gl_add_line_count_key(scope_id)
    nlines = int(st.session_state.get(nkey, 2) or 2)
    if nlines < 2:
        st.session_state[nkey] = 2
        nlines = 2

    anchor_ers = [er for er, _ in anchor_opts]
    anchor_labels = [lbl for _, lbl in anchor_opts]

    with st.expander(tr("Add GL entry"), expanded=False):
        st.caption(
            tr(
                "Balanced compound journal (like **Entries & invoices**). Lines are added to the grid below "
                "the chosen workbook row; click **Save changes** to write the master workbook."
            )
        )
        sel_idx = st.selectbox(
            tr("Insert below row"),
            range(len(anchor_opts)),
            format_func=lambda i: anchor_labels[i],
            key=f"fin_gl_add_anchor_{scope_id}",
        )
        insert_after = anchor_ers[int(sel_idx)]

        details = st.text_area(tr("Details"), key=f"fin_gl_add_details_{scope_id}", height=72)
        if details.strip():
            sug = db.suggest_accounts_from_description(client, details, limit=5)
            if sug:
                st.markdown(tr("**Quick picks** (first debit / first credit line)"))
                for i, r in enumerate(sug):
                    lbl = f"{r['keyword']}: **{r['debit_account']}** / **{r['credit_account']}**"
                    if st.button(lbl, key=f"fin_gl_add_sug_{scope_id}_{i}"):
                        st.session_state[_gl_add_line_keys(scope_id, 0)[0]] = r["debit_account"]
                        st.session_state[_gl_add_line_keys(scope_id, 1)[0]] = r["credit_account"]
                        st.rerun(scope="fragment")

        _sync_gl_add_posting_date_to_anchor(
            scope_id,
            editor_df,
            insert_after,
            default_posting_date,
            include_tr=include_tr,
        )
        posting = st.date_input(
            tr("Posting date"),
            key=_gl_add_date_key(scope_id),
        )

        tr_override = ""
        if include_tr:
            peek_key = f"fin_gl_add_peek_tr_{scope_id}"
            peek = st.session_state.get(peek_key)
            if peek is None:
                with st.spinner("Reading suggested transaction number…"):
                    peek = gl_wb.peek_next_transaction_number(client, dict(secrets))
                st.session_state[peek_key] = peek
            sug_tr, has_tr, perr = peek
            if st.button(tr("Refresh Tr. no."), key=f"fin_gl_add_tr_refresh_{scope_id}"):
                st.session_state.pop(peek_key, None)
                st.rerun(scope="fragment")
            if perr:
                st.caption(f"Could not read transaction numbers: {perr}")
            elif has_tr:
                st.caption(f"Next transaction number if override is blank: **{sug_tr}**")
            tr_override = st.text_input(
                tr("Transaction number (optional override)"),
                key=f"fin_gl_add_tr_{scope_id}",
                placeholder=tr("Leave blank for automatic numbering on save"),
            )

        st.markdown(tr("**Line items**"))
        for i in range(nlines):
            ka, kd, kc = _gl_add_line_keys(scope_id, i)
            st.markdown(tr(f"**Line {i + 1}**"))
            lc1, lc2, lc3 = st.columns([2.6, 1, 1])
            with lc1:
                st.text_input(tr("Account"), key=ka, placeholder=tr("e.g. 6200-utilities"))
            with lc2:
                st.text_input(tr("Debit"), key=kd, placeholder="0.00")
            with lc3:
                st.text_input(tr("Credit"), key=kc, placeholder="0.00")

        b1, b2, _sp = st.columns([1, 1, 2])
        with b1:
            if st.button(tr("＋ Line"), key=f"fin_gl_add_plus_{scope_id}", disabled=nlines >= _MAX_GL_ADD_LINES):
                st.session_state[nkey] = nlines + 1
                st.rerun(scope="fragment")
        with b2:
            if st.button(tr("－ Last line"), key=f"fin_gl_add_minus_{scope_id}", disabled=nlines <= 2):
                li = nlines - 1
                for k in _gl_add_line_keys(scope_id, li):
                    st.session_state.pop(k, None)
                st.session_state[nkey] = nlines - 1
                st.rerun(scope="fragment")

        if not st.button(tr("Add to grid"), type="secondary", key=f"fin_gl_add_submit_{scope_id}"):
            return None, None

        if not str(details or "").strip():
            st.error(tr("Enter details for this entry."))
            return None, None
        lines_raw = _gather_gl_add_lines(scope_id, nlines)
        try:
            normed = db.normalize_journal_lines_for_insert(lines_raw)
        except ValueError as e:
            st.error(str(e))
            return None, None

        tr_val: str | None = str(tr_override or "").strip() or None
        editor_recs, order_err = _finalize_editor_records_or_error(
            editor_df.to_dict(orient="records"),
            scope_id=scope_id,
            include_tr=include_tr,
        )
        if order_err:
            st.error(order_err)
            return None, None
        assert editor_recs is not None
        resolved_after = _resolve_insert_after_in_editor_records(
            editor_recs, insert_after, include_tr=include_tr
        )
        if resolved_after != insert_after:
            st.caption(
                f"Insert will land below row **{resolved_after}** (bottom of that journal entry). "
                f"You selected row **{insert_after}**."
            )
        new_line_rows = _editor_rows_from_compound_entry(
            scope_id=scope_id,
            insert_after=resolved_after,
            posting_date=posting,
            details=str(details).strip(),
            journal_lines=normed,
            include_tr=include_tr,
            transaction_number=tr_val,
        )
        try:
            placed = _insert_compound_below_anchor(
                editor_recs,
                insert_after=insert_after,
                new_rows=new_line_rows,
                include_tr=include_tr,
            )
        except ValueError as e:
            st.error(str(e))
            return None, None
        merged_recs, order_err = _finalize_editor_records_or_error(
            placed,
            scope_id=scope_id,
            include_tr=include_tr,
        )
        if order_err:
            st.error(order_err)
            return None, None
        assert merged_recs is not None
        first_idx = _first_new_row_display_index(merged_recs, resolved_after)
        return pd.DataFrame(merged_recs), first_idx


def _strip_ui_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Drop display-only columns from ``st.data_editor`` returns before merge/save."""
    drop = [c for c in df.columns if c == "row_num"]
    if drop:
        return df.drop(columns=drop, errors="ignore")
    return df


def _merge_new_lines_into_records(
    base_recs: list[dict[str, Any]],
    new_recs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Place ``_excel_row`` 0 lines below their ``After row`` anchor (display order)."""
    if not new_recs:
        return list(base_recs)
    out = list(base_recs)
    i = 0
    while i < len(new_recs):
        after = _excel_row_int(new_recs[i].get("After row"))
        block: list[dict[str, Any]] = []
        while i < len(new_recs) and _excel_row_int(new_recs[i].get("After row")) == after:
            block.append(dict(new_recs[i]))
            i += 1
        if after > 0 and block:
            out = _insert_compound_below_anchor(
                out,
                insert_after=after,
                new_rows=block,
                resolve_block_end=False,
            )
        else:
            out.extend(block)
    return out


def _merge_cell_edits_by_excel_row(
    editor_df: pd.DataFrame,
    edited_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Apply cell edits from ``st.data_editor`` without accepting Streamlit row drops.

    Existing lines match on ``_excel_row``; pending inserts (``_excel_row`` 0) match in
    display order so anchors and text are not shifted onto the wrong line.
    """
    stripped = _strip_ui_columns(edited_df)
    merge_cols = [c for c in editor_df.columns if c in stripped.columns or c == "_excel_row"]
    if not merge_cols:
        return editor_df

    base = editor_df.reset_index(drop=True)
    patch_recs = stripped.to_dict(orient="records")
    base_recs = base.to_dict(orient="records")

    patch_by_er: dict[int, dict[str, Any]] = {}
    patch_by_pending_id: dict[int, dict[str, Any]] = {}
    patch_new_fifo: list[dict[str, Any]] = []
    for prec in patch_recs:
        er = _excel_row_int(prec.get("_excel_row"))
        if er > 0:
            patch_by_er[er] = prec
        else:
            pid = _excel_row_int(prec.get("_excel_row"))
            if pid < 0:
                patch_by_pending_id[pid] = prec
            else:
                patch_new_fifo.append(prec)

    patched: list[dict[str, Any]] = []
    fifo_i = 0
    for b in base_recs:
        er = _excel_row_int(b.get("_excel_row"))
        if er > 0:
            p = patch_by_er.get(er)
            if p is not None:
                patched.append(_merge_patch_into_row(b, p, merge_cols))
            else:
                patched.append(dict(b))
        else:
            pid = _excel_row_int(b.get("_excel_row"))
            p = patch_by_pending_id.get(pid)
            if p is None and fifo_i < len(patch_new_fifo):
                p = patch_new_fifo[fifo_i]
                fifo_i += 1
            if p is not None:
                patched.append(_merge_patch_into_row(b, p, merge_cols))
            else:
                patched.append(dict(b))
    while fifo_i < len(patch_new_fifo):
        patched = _merge_new_lines_into_records(patched, [patch_new_fifo[fifo_i]])
        fifo_i += 1
    return _merge_edited_with_after_row(
        base,
        pd.DataFrame(_canonicalize_editor_display_order(patched)),
    )


def _baseline_window_fingerprint(baseline: pd.DataFrame) -> str:
    ers = sorted(_excel_rows_in_df(_editable_baseline_df(baseline)))
    if not ers:
        return "empty"
    return f"{len(ers)}:{ers[0]}:{ers[-1]}"


def _ensure_edit_baseline(
    *,
    cache_gen: int,
    scope_id: str,
    baseline: pd.DataFrame,
) -> pd.DataFrame:
    """Persist and return the editable baseline window (matches the grid row cap)."""
    snap_key = _baseline_snap_key(cache_gen, scope_id)
    fp_key = f"{snap_key}_fp"
    fp = _baseline_window_fingerprint(baseline)
    if st.session_state.get(fp_key) != fp:
        st.session_state.pop(snap_key, None)
        st.session_state.pop(_local_edit_key(cache_gen, scope_id), None)
        st.session_state.pop(_editor_widget_key(cache_gen, scope_id), None)
        _prune_pending_to_baseline(scope_id, baseline)
        st.session_state[fp_key] = fp

    snap = st.session_state.get(snap_key)
    if isinstance(snap, list) and snap:
        return pd.DataFrame(snap)
    editable = _editable_baseline_df(baseline)
    st.session_state[snap_key] = editable.to_dict(orient="records")
    return editable


def _seen_excel_rows(df: pd.DataFrame) -> set[int]:
    out: set[int] = set()
    if df.empty or "_excel_row" not in df.columns:
        return out
    for rec in df.to_dict(orient="records"):
        er = _excel_row_int(rec.get("_excel_row"))
        if er > 0:
            out.add(er)
    return out


def _explicit_delete_rows(
    *,
    baseline: pd.DataFrame,
    marked_del: list[int],
) -> list[int]:
    """Legacy helper: explicit row list scoped to the editable baseline window."""
    scope = _excel_rows_in_df(baseline)
    return sorted({int(er) for er in marked_del if int(er) in scope})


def _row_delete_label(rec: dict[str, Any]) -> str:
    er = _excel_row_int(rec.get("_excel_row"))
    acct = str(rec.get("Account") or "").strip()[:40]
    return f"Row {er}" + (f" — {acct}" if acct else "")


def _workbook_rows_in_editor_scope(
    slice_raw: list[dict[str, Any]],
    *,
    include_tr: bool,
) -> set[int]:
    """Excel row numbers in the current Financials slice (after cache refresh)."""
    frame = gled.records_to_editor_frame(slice_raw, include_tr=include_tr)
    return _excel_rows_in_df(_editable_baseline_df(frame))


def _apply_batch_row_delete(
    client: Any,
    secrets: dict[str, Any],
    *,
    cache_gen: int,
    scope_id: str,
    excel_rows: list[int],
    merged: pd.DataFrame,
    gl_sheet_name: str,
    layout: dict[str, Any] | None,
    slice_raw: list[dict[str, Any]],
    include_tr: bool,
) -> bool:
    """Clear selected workbook rows (faux delete). Keeps other unsaved grid edits."""
    scope = _workbook_rows_in_editor_scope(slice_raw, include_tr=include_tr)
    chosen = sorted({int(x) for x in excel_rows if int(x) > 0})
    if not chosen:
        st.warning("Select at least one row to remove.")
        return False
    if len(chosen) > _MAX_DELETE_BATCH:
        st.error(f"Select at most **{_MAX_DELETE_BATCH}** rows at once.")
        return False

    out_of_scope = [er for er in chosen if er not in scope]
    if out_of_scope:
        st.error(
            f"Row(s) {out_of_scope[:8]} are not in the current GL view. "
            "Refresh or reselect from the list below the grid."
        )
        return False

    by_er = {
        _excel_row_int(r.get("_excel_row")): r
        for r in merged.to_dict(orient="records")
        if _excel_row_int(r.get("_excel_row")) > 0
    }
    targets: list[dict[str, Any]] = []
    for er in chosen:
        rec = by_er.get(er, {})
        targets.append(
            {
                "excel_row": er,
                "account": str(rec.get("Account") or ""),
                "debit": float(rec.get("Debit") or 0),
                "credit": float(rec.get("Credit") or 0),
            }
        )
    label = ", ".join(f"{t['excel_row']} ({t['account']})" for t in targets if t.get("account")) or ", ".join(
        str(t["excel_row"]) for t in targets
    )
    with st.spinner(f"Removing {len(chosen)} ledger line(s)…"):
        err = gled.persist_gl_row_deletes(
            client,
            secrets,
            targets,
            sheet_name=gl_sheet_name,
            layout=layout,
        )
    if err:
        st.error(err)
        return False

    chosen_set = set(chosen)
    _record_faux_deleted_rows(scope_id, chosen_set)
    _drop_pending_rows(scope_id, chosen_set)
    scope_rows = _workbook_rows_in_editor_scope(slice_raw, include_tr=include_tr) - chosen_set
    cached = st.session_state.get("master_gl_rows_raw")
    fresh_slice: list[dict[str, Any]] = []
    if isinstance(cached, list):
        fresh_slice = [
            r
            for r in cached
            if isinstance(r.get("_excel_row"), int) and int(r["_excel_row"]) in scope_rows
        ]
    post_delete_baseline = _editable_baseline_df(
        gled.records_to_editor_frame(fresh_slice, include_tr=include_tr)
    )
    rebuilt = _rebuild_pending_after_delete(
        scope_id,
        post_delete_baseline,
        chosen_set,
        include_tr=include_tr,
    )
    _reset_gl_editor_workspace_after_delete(
        cache_gen,
        scope_id,
        include_tr=include_tr,
        deleted=chosen_set,
        baseline=post_delete_baseline,
        rebuilt=rebuilt,
    )
    st.session_state[_edit_mode_scope_key(scope_id)] = True
    # Pending edits on remaining rows are kept (pruned in _drop_pending_rows above).
    st.success(f"Deleted **{len(chosen)}** row(s): {label}. Unsaved edits on other rows are kept — use **Save changes**.")
    return True


def _render_gl_edit_toolbar(
    *,
    client: Any,
    secrets: dict[str, Any],
    merged: pd.DataFrame,
    cache_gen: int,
    scope_id: str,
    gl_sheet_name: str,
    layout: dict[str, Any] | None,
    slice_raw: list[dict[str, Any]],
    include_tr: bool,
    editable_baseline: pd.DataFrame,
    has_new: bool,
) -> tuple[bool, bool, bool]:
    """
    Row picker, **Delete rows**, and **Save changes** on one line.

    Returns ``(delete_rerun, save_clicked, discard_clicked)``.
    """
    allowed = sorted(_excel_rows_in_df(editable_baseline))
    by_er = {
        _excel_row_int(r.get("_excel_row")): r
        for r in merged.to_dict(orient="records")
        if _excel_row_int(r.get("_excel_row")) > 0
    }

    pick_col, del_col, save_col = st.columns([5, 1.15, 1.15])
    selected: list[int] = []
    with pick_col:
        if allowed:
            selected = st.multiselect(
                "Rows to delete",
                options=allowed,
                format_func=lambda er: _row_delete_label(by_er.get(er, {"_excel_row": er})),
                key=f"fin_gl_del_multi_{cache_gen}_{scope_id}",
                placeholder="Select row numbers…",
            )
        else:
            st.multiselect(
                "Rows to delete",
                options=[],
                placeholder="No rows in this slice",
                disabled=True,
                key=f"fin_gl_del_multi_{cache_gen}_{scope_id}",
            )
    with del_col:
        st.write("")
        delete_clicked = st.button(
            tr("Delete rows"),
            type="secondary",
            key=f"fin_gl_del_now_{cache_gen}_{scope_id}",
            disabled=not selected,
            width="stretch",
        )
    with save_col:
        st.write("")
        save_clicked = st.button(
            tr("Save changes"),
            type="primary",
            key=f"fin_gl_save_{cache_gen}_{scope_id}",
            width="content",
        )

    discard_clicked = False
    if has_new:
        discard_clicked = st.button(
            tr("Discard new lines"),
            key=f"fin_gl_discard_new_{cache_gen}_{scope_id}",
            width="content",
        )

    if delete_clicked:
        return (
            _apply_batch_row_delete(
                client,
                secrets,
                cache_gen=cache_gen,
                scope_id=scope_id,
                excel_rows=selected,
                merged=merged,
                gl_sheet_name=gl_sheet_name,
                layout=layout,
                slice_raw=slice_raw,
                include_tr=include_tr,
            ),
            False,
            False,
        )
    return False, save_clicked, discard_clicked


def _widget_overlay_is_stale(editor_df: pd.DataFrame, widget_df: pd.DataFrame) -> bool:
    """True when widget session state would clobber good pending rows if merged naively."""
    if widget_df.empty:
        return True
    if len(widget_df) < len(editor_df):
        return True
    if _widget_amounts_spuriously_zeroed(editor_df, widget_df) and not _grid_has_real_text_edits(
        editor_df, widget_df
    ):
        return True
    return False


def _merged_from_pending(
    scope_id: str,
    workbook_baseline: pd.DataFrame,
) -> pd.DataFrame | None:
    """Last stashed grid snapshot (previous fragment run) when widget state lags."""
    raw = st.session_state.get(_pending_edits_key(scope_id))
    if not isinstance(raw, list) or not raw:
        return None
    repaired = _repair_pending_amounts(workbook_baseline, raw)
    return _clamp_editor_to_baseline(
        _apply_pending_over_baseline(workbook_baseline, repaired, scope_id=scope_id),
        workbook_baseline,
    )


def _grid_has_pending_new_rows(df: pd.DataFrame) -> bool:
    if df.empty:
        return False
    for rec in df.to_dict(orient="records"):
        if _is_pending_insert_row(rec):
            return True
    return False


def _best_merged_for_save(
    merged: pd.DataFrame,
    *,
    cache_gen: int,
    scope_id: str,
    workbook_baseline: pd.DataFrame,
) -> pd.DataFrame:
    """
    Prefer stashed grid snapshots when ``st.data_editor`` omits pending new lines.

    Faux-delete tracking alone must not satisfy Save — new rows live in pending/snap.
    """
    if _grid_has_pending_new_rows(merged):
        return merged
    alt = _merged_from_pending(scope_id, workbook_baseline)
    if alt is not None and _grid_has_pending_new_rows(alt):
        return alt
    snap = st.session_state.get(_merged_snap_key(cache_gen, scope_id))
    if isinstance(snap, list) and snap:
        snap_df = pd.DataFrame(snap)
        if _grid_has_pending_new_rows(snap_df):
            return snap_df
    return merged


def _safe_stash_pending_edits(
    scope_id: str,
    merged: pd.DataFrame,
    *,
    baseline: pd.DataFrame | None = None,
) -> None:
    """Keep prior pending when this run's widget merge dropped ``Row #`` 0 lines."""
    key = _pending_edits_key(scope_id)
    prev = st.session_state.get(key)
    if (
        isinstance(prev, list)
        and prev
        and _grid_has_pending_new_rows(pd.DataFrame(prev))
        and not _grid_has_pending_new_rows(merged)
    ):
        return
    _stash_pending_edits(scope_id, merged, baseline=baseline)


def _safe_write_merged_snap(
    cache_gen: int,
    scope_id: str,
    merged: pd.DataFrame,
) -> None:
    """Do not replace a good add-entry snap with a baseline-only widget return."""
    snap_key = _merged_snap_key(cache_gen, scope_id)
    prev = st.session_state.get(snap_key)
    if (
        isinstance(prev, list)
        and prev
        and _grid_has_pending_new_rows(pd.DataFrame(prev))
        and not _grid_has_pending_new_rows(merged)
    ):
        return
    st.session_state[snap_key] = merged.to_dict(orient="records")


def _plan_change_count(plan: xleng.GlEditPlan) -> int:
    return len(plan.updates) + len(plan.insert_rows) + len(plan.swap_rows)


def _plan_from_merged(
    baseline: pd.DataFrame,
    merged: pd.DataFrame,
    *,
    include_tr: bool,
    scope_id: str = "",
) -> xleng.GlEditPlan:
    from workbook_editor.gl_edit_state import build_gl_edit_plan

    faux_del = _faux_deleted_rows(scope_id) if scope_id else set()
    edited_recs = [
        dict(r)
        for r in merged.to_dict(orient="records")
        if _excel_row_int(r.get("_excel_row")) <= 0 or _excel_row_int(r.get("_excel_row")) not in faux_del
    ]
    wb_recs = _master_gl_workbook_records()
    plan = build_gl_edit_plan(
        baseline.to_dict(orient="records"),
        edited_recs,
        include_tr=include_tr,
        delete_excel_rows=faux_del,
        workbook_records=wb_recs,
    )
    # Re-clear faux-deleted lines only when new rows are inserted (row shifts can resurrect ghosts).
    if faux_del and plan.insert_rows:
        plan.delete_rows = sorted(set(plan.delete_rows) | faux_del)
    return plan


def _exit_edit_mode(cache_gen: int, scope_id: str) -> None:
    _clear_scope_state(cache_gen, scope_id)


def _handle_save(
    client: Any,
    secrets: dict[str, Any],
    *,
    cache_gen: int,
    scope_id: str,
    include_tr: bool,
    gl_sheet_name: str,
    layout: dict[str, Any] | None,
    editable_baseline: pd.DataFrame,
    merged: pd.DataFrame,
) -> bool:
    """Save edits (if any), exit edit mode, refresh. Returns True when the page should rerun."""
    workbook_baseline = _editable_baseline_df(editable_baseline)
    merged_for_plan = _best_merged_for_save(
        merged,
        cache_gen=cache_gen,
        scope_id=scope_id,
        workbook_baseline=workbook_baseline,
    )
    merged_for_plan = _merge_cell_edits_by_excel_row(workbook_baseline, merged_for_plan)
    faux_del = _faux_deleted_rows(scope_id) if scope_id else set()
    plan_recs, order_err = _finalize_editor_records_or_error(
        merged_for_plan.to_dict(orient="records"),
        scope_id=scope_id,
        include_tr=include_tr,
    )
    if order_err:
        st.error(order_err)
        return False
    assert plan_recs is not None
    plan_recs = _project_coherent_row_numbers_on_save(
        plan_recs,
        faux_deleted=faux_del,
    )
    merged_for_plan = pd.DataFrame(plan_recs)
    plan = _plan_from_merged(
        workbook_baseline,
        merged_for_plan,
        include_tr=include_tr,
        scope_id=scope_id,
    )
    if _plan_change_count(plan) == 0:
        snap = st.session_state.get(_merged_snap_key(cache_gen, scope_id))
        if isinstance(snap, list) and snap:
            snap_df = pd.DataFrame(snap)
            snap_plan = _plan_from_merged(
                workbook_baseline,
                snap_df,
                include_tr=include_tr,
                scope_id=scope_id,
            )
            if _plan_change_count(snap_plan) > 0:
                merged_for_plan = snap_df
                plan = snap_plan
    if _plan_change_count(plan) == 0:
        alt = _merged_from_pending(scope_id, workbook_baseline)
        if alt is not None:
            alt_plan = _plan_from_merged(
                workbook_baseline,
                alt,
                include_tr=include_tr,
                scope_id=scope_id,
            )
            if _plan_change_count(alt_plan) > 0:
                merged_for_plan = alt
                plan = alt_plan
    if _plan_change_count(plan) == 0:
        st.warning(
            "No further edits to save (row deletes are already written when you click **Delete rows**). "
            "If you changed cells, click outside the edited cell, then **Save changes** again."
        )
        return False

    with st.spinner("Saving to master workbook…"):
        err = gled.persist_gl_edit_plan(
            client,
            secrets,
            plan,
            sheet_name=gl_sheet_name,
            layout=layout,
        )
    if err:
        st.error(err)
        return False

    new_gen = int(st.session_state.get("workbook_cache_gen") or cache_gen)
    _clear_pending_edits(scope_id)
    _clear_faux_deleted_rows(scope_id)
    _exit_edit_mode(new_gen, scope_id)
    st.success("GL saved.")
    return True


def render_gl_table_section(
    client: Any,
    secrets: dict[str, Any],
    *,
    slice_raw: list[dict[str, Any]],
    layout: dict[str, Any] | None,
    gl_sheet_name: str,
    object_path: str,
    include_tr: bool,
    cache_gen: int,
    scope_sig: str,
    is_admin: bool,
    default_posting_date: date | None = None,
) -> None:
    """Read-only GL; admins get **Edit GL** below the table."""
    scope_id = _scope_id(scope_sig)
    _ensure_scope(cache_gen, scope_id)

    baseline = gled.records_to_editor_frame(slice_raw, include_tr=include_tr)
    edit_on = bool(is_admin and st.session_state.get(_edit_mode_scope_key(scope_id)))
    posting_default = default_posting_date if default_posting_date is not None else date.today()

    if edit_on:
        st.caption(
            tr(
                "Each line shows a provisional **Row #** (new lines show their future slot; existing lines keep "
                "workbook numbers until **Save changes**). Use **Add GL entry** for balanced journals; "
                "**Delete rows** clears lines. Press **Enter** or click outside a cell, then **Save changes**."
            )
        )
        if _gl_edit_fragment(
            client=client,
            secrets=secrets,
            baseline=baseline,
            slice_raw=slice_raw,
            include_tr=include_tr,
            cache_gen=cache_gen,
            scope_id=scope_id,
            gl_sheet_name=gl_sheet_name,
            layout=layout,
            default_posting_date=posting_default,
        ):
            st.rerun()
    else:
        render_readonly_table(slice_raw, client=client, include_tr=include_tr)

    if not is_admin:
        return

    if not xleng.path_supports_gl_append(object_path):
        st.caption(tr("Link an `.xlsx` or `.xlsm` workbook in **Settings** to enable in-app GL editing."))
        return

    if not edit_on:
        if st.button(tr("Edit GL"), type="primary", key=f"fin_gl_edit_open_{cache_gen}_{scope_id}"):
            st.session_state[_edit_mode_scope_key(scope_id)] = True
            _reset_edit_workspace(cache_gen, scope_id, keep_edit_mode=True)
            st.rerun()


@st.fragment
def _gl_edit_fragment(
    *,
    client: Any,
    secrets: dict[str, Any],
    baseline: pd.DataFrame,
    slice_raw: list[dict[str, Any]],
    include_tr: bool,
    cache_gen: int,
    scope_id: str,
    gl_sheet_name: str,
    layout: dict[str, Any] | None,
    default_posting_date: date,
) -> bool:
    """Editable grid + save (same fragment so widget state is current). Returns True after a successful save."""
    if baseline.empty and not st.session_state.get(_local_edit_key(cache_gen, scope_id)):
        st.info(tr("No editable GL lines in this slice."))
        return False

    editable_baseline = _ensure_edit_baseline(
        cache_gen=cache_gen,
        scope_id=scope_id,
        baseline=baseline,
    )
    editor_df = _load_editor_df(
        cache_gen=cache_gen,
        scope_id=scope_id,
        baseline=editable_baseline,
    )
    workbook_slice_base = _editable_baseline_df(baseline)
    if len(baseline) > _MAX_EDIT_ROWS:
        st.warning(
            tr(
                f"Showing the last **{_MAX_EDIT_ROWS}** lines in the editor "
                f"(of **{len(baseline)}** in this slice). Only those lines can be edited or removed — "
                "narrow **Rows shown** on Financials to reach earlier lines."
            )
        )

    data_cols = ["_excel_row", "After row", "row_num", "Date", "Account", "Debit", "Credit", "Details"]
    if include_tr:
        data_cols.append("Tr")
    grid_cols = ["row_num", "Date", "Account", "Debit", "Credit", "Details"]
    if include_tr:
        grid_cols.append("Tr")
    hidden_cols = ["_excel_row", "After row"]

    editor_window = editor_df.reset_index(drop=True)
    for col in data_cols:
        if col not in editor_window.columns:
            editor_window[col] = 0 if col in ("After row", "row_num", "_excel_row") else ""
    display_df = gled.normalize_editor_dataframe_dtypes(
        _dataframe_for_grid_display(editor_window[data_cols].copy()),
        include_tr=include_tr,
    )
    widget_key = _editor_widget_key(cache_gen, scope_id)

    widget_raw = st.session_state.get(widget_key)
    if isinstance(widget_raw, pd.DataFrame):
        widget_strip = _strip_ui_columns(widget_raw)
        if _widget_amounts_spuriously_zeroed(editor_window, widget_strip) and not _grid_has_real_text_edits(
            editor_window, widget_strip
        ):
            fixed = _merge_cell_edits_by_excel_row(editor_window, widget_strip)
            _stash_pending_edits(scope_id, fixed, baseline=workbook_slice_base)
            editor_df = _load_editor_df(
                cache_gen=cache_gen,
                scope_id=scope_id,
                baseline=editable_baseline,
            )
            editor_window = editor_df.reset_index(drop=True)
            display_df = gled.normalize_editor_dataframe_dtypes(
                _dataframe_for_grid_display(editor_window[data_cols].copy()),
                include_tr=include_tr,
            )
            st.session_state.pop(widget_key, None)

    with st.container(border=True):
        st.caption(tr("Ledger lines — scroll inside the grid for long slices."))
        edited = st.data_editor(
            display_df,
            height=_gl_editor_scroll_height(len(display_df)),
            column_order=grid_cols + hidden_cols,
            column_config={
                "row_num": st.column_config.NumberColumn(
                    "Row #",
                    help=(
                        "Provisional line number while editing. New lines show where they will land; "
                        "all rows are renumbered to match the workbook on **Save changes**."
                    ),
                    min_value=0,
                    step=1,
                    format="%d",
                    default=0,
                    disabled=True,
                ),
                "_excel_row": st.column_config.NumberColumn(
                    "ID",
                    help="Internal row key (read-only).",
                    format="%d",
                    disabled=True,
                ),
                "After row": st.column_config.NumberColumn(
                    "After row",
                    help="Insert anchor (read-only).",
                    min_value=0,
                    step=1,
                    format="%d",
                    default=0,
                    disabled=True,
                ),
                "Date": st.column_config.TextColumn("Date"),
                "Account": st.column_config.TextColumn("Account"),
                "Debit": st.column_config.NumberColumn("Debit", format="%.2f"),
                "Credit": st.column_config.NumberColumn("Credit", format="%.2f"),
                "Details": st.column_config.TextColumn("Details"),
                **({"Tr": st.column_config.TextColumn("Tr. no.")} if include_tr else {}),
            },
            hide_index=True,
            width="stretch",
            num_rows="fixed",
            key=widget_key,
        )

    stripped_edit = _patch_from_editor_return(edited)

    if len(stripped_edit) < len(display_df):
        st.session_state.pop(widget_key, None)
        st.warning(
            "The grid lost rows due to a Streamlit sync glitch. It was reset — re-enter edits. "
            "Use **Delete rows** below the grid to remove lines."
        )
        st.rerun(scope="fragment")
        return False

    if _widget_overlay_is_stale(editor_window, stripped_edit) and not _grid_has_real_text_edits(
        editor_window, stripped_edit
    ):
        merged = editor_window.reset_index(drop=True)
    else:
        merged = _merge_cell_edits_by_excel_row(editor_window, stripped_edit)
    merged = pd.DataFrame(
        _canonicalize_editor_display_order(merged.to_dict(orient="records"), scope_id=scope_id)
    )

    has_new = _grid_has_pending_new_rows(merged)

    added_df, _first_new_idx = _try_add_compound_from_form(
        client=client,
        secrets=secrets,
        scope_id=scope_id,
        editor_df=merged,
        include_tr=include_tr,
        default_posting_date=default_posting_date,
    )
    if added_df is not None:
        _persist_editor_df(cache_gen=cache_gen, scope_id=scope_id, df=added_df)
        _stash_pending_edits(scope_id, added_df, baseline=workbook_slice_base)
        st.session_state[_merged_snap_key(cache_gen, scope_id)] = added_df.to_dict(orient="records")
        st.session_state.pop(_editor_widget_key(cache_gen, scope_id), None)
        _bump_editor_widget_nonce(scope_id)
        st.success("Added lines to the grid — click **Save changes** when ready.")
        st.rerun(scope="fragment")
        return False

    delete_rerun, save_clicked, discard_clicked = _render_gl_edit_toolbar(
        client=client,
        secrets=secrets,
        merged=merged,
        cache_gen=cache_gen,
        scope_id=scope_id,
        gl_sheet_name=gl_sheet_name,
        layout=layout,
        slice_raw=slice_raw,
        include_tr=include_tr,
        editable_baseline=editable_baseline,
        has_new=has_new,
    )

    if save_clicked:
        wb_base = workbook_slice_base
        save_merged = _best_merged_for_save(
            merged,
            cache_gen=cache_gen,
            scope_id=scope_id,
            workbook_baseline=wb_base,
        )
        if _handle_save(
            client,
            secrets,
            cache_gen=cache_gen,
            scope_id=scope_id,
            include_tr=include_tr,
            gl_sheet_name=gl_sheet_name,
            layout=layout,
            editable_baseline=editable_baseline,
            merged=save_merged,
        ):
            return True

    if discard_clicked:
        _clear_pending_edits(scope_id)
        _clear_faux_deleted_rows(scope_id)
        _persist_editor_df(cache_gen=cache_gen, scope_id=scope_id, df=editable_baseline)
        st.session_state.pop(_editor_widget_key(cache_gen, scope_id), None)
        st.session_state.pop(_merged_snap_key(cache_gen, scope_id), None)
        st.rerun(scope="fragment")

    if delete_rerun:
        return True

    _safe_stash_pending_edits(scope_id, merged, baseline=workbook_slice_base)
    _safe_write_merged_snap(cache_gen, scope_id, merged)

    return False


def render_readonly_table(
    slice_raw: list[dict[str, Any]],
    *,
    client: Any,
    include_tr: bool,
) -> None:
    import database as db

    if include_tr:
        rows_show = []
        for r in slice_raw:
            rows_show.append(
                {
                    "Tr": str(r.get("transaction_number") or "").strip(),
                    "Date": str(r.get("gl_date") or "")[:32],
                    "Account": str(r.get("account") or ""),
                    "Debit": r.get("debit"),
                    "Credit": r.get("credit"),
                    "Details": str(r.get("description") or ""),
                }
            )
        st.dataframe(pd.DataFrame(rows_show), width="stretch", hide_index=True)
    else:
        jrows = xleng.gl_flat_records_to_journal_display_rows(
            slice_raw, display_currency_iso=db.fetch_display_currency_iso(client)
        )
        st.dataframe(pd.DataFrame(jrows), width="stretch", hide_index=True)
