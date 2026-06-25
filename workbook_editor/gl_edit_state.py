"""
GL row edit state for Streamlit (explicit deletes; no grid-diff inference).

Parsing / persistence still use existing ``excel_engine`` + ``gl_editor``; this module only
builds edit plans from plain row dicts.
"""

from __future__ import annotations

from typing import Any

import gl_editor as gled


def _excel_row(rec: dict[str, Any]) -> int:
    try:
        return int(rec.get("_excel_row") or 0)
    except (TypeError, ValueError):
        return 0


def editable_scope(rows: list[dict[str, Any]]) -> set[int]:
    return {er for rec in rows if (er := _excel_row(rec)) > 0}


def build_gl_edit_plan(
    baseline_rows: list[dict[str, Any]],
    edited_rows: list[dict[str, Any]],
    *,
    include_tr: bool,
    delete_excel_rows: list[int] | set[int],
    workbook_records: list[dict[str, Any]] | None = None,
) -> Any:
    """
    Build a :class:`~excel_engine.GlEditPlan` from row dicts.

    ``delete_excel_rows`` must list only rows the user explicitly queued — never inferred
    from a shorter grid.
    """
    import pandas as pd

    import excel_engine as xleng

    baseline = pd.DataFrame(baseline_rows) if baseline_rows else pd.DataFrame()
    scope = editable_scope(baseline_rows)
    scoped_del = sorted({int(x) for x in delete_excel_rows if int(x) in scope})

    edited = pd.DataFrame(edited_rows) if edited_rows else pd.DataFrame()
    if scoped_del and not edited.empty and "_excel_row" in edited.columns:
        drop = set(scoped_del)
        edited = edited[~edited["_excel_row"].astype(int).isin(drop)].reset_index(drop=True)

    plan = gled.plan_from_editor_diff(
        baseline,
        edited,
        include_tr=include_tr,
        delete_scope=scope,
        infer_deletes=False,
        workbook_records=workbook_records,
    )
    plan.delete_rows = scoped_del
    return plan
