"""Faux-deleted rows must stay cleared when Save also inserts new lines."""

from __future__ import annotations

import pandas as pd

from views.gl_sheet_editor import _plan_from_merged


def test_save_plan_reclears_faux_deleted_rows() -> None:
    baseline = pd.DataFrame(
        [
            {
                "_excel_row": 10,
                "After row": 0,
                "Date": "2025-01-01",
                "Account": "Cash",
                "Debit": 100.0,
                "Credit": 0.0,
                "Details": "a",
            },
            {
                "_excel_row": 12,
                "After row": 0,
                "Date": "2025-01-03",
                "Account": "Rent",
                "Debit": 0.0,
                "Credit": 50.0,
                "Details": "b",
            },
        ]
    )
    merged_recs = [
        {
            "_excel_row": 10,
            "After row": 0,
            "Date": "2025-01-01",
            "Account": "Cash",
            "Debit": 100.0,
            "Credit": 0.0,
            "Details": "a",
        },
        {
            "_excel_row": 0,
            "After row": 10,
            "Date": "2025-01-02",
            "Account": "Fees",
            "Debit": 25.0,
            "Credit": 0.0,
            "Details": "new",
        },
        {
            "_excel_row": 0,
            "After row": 10,
            "Date": "",
            "Account": "Bank",
            "Debit": 0.0,
            "Credit": 25.0,
            "Details": "",
        },
        {
            "_excel_row": 12,
            "After row": 0,
            "Date": "2025-01-03",
            "Account": "Rent",
            "Debit": 0.0,
            "Credit": 50.0,
            "Details": "b",
        },
    ]
    import streamlit as st

    from views import gl_sheet_editor as gse

    scope = "faux_del_insert_scope"
    key = gse._faux_deleted_rows_key(scope)
    st.session_state[key] = [11]
    try:
        plan = _plan_from_merged(
            baseline,
            pd.DataFrame(merged_recs),
            include_tr=False,
            scope_id=scope,
        )
    finally:
        st.session_state.pop(key, None)

    assert 11 in plan.delete_rows
    assert len(plan.insert_rows) == 2
    assert not any(
        (spec.get("account") or "").strip() == "Gone"
        for spec in plan.insert_rows + plan.updates
    )
