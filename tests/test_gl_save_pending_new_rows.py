"""Save must apply pending new lines even when the data_editor return omits them."""

from __future__ import annotations

import pandas as pd

from views.gl_sheet_editor import _best_merged_for_save, _plan_from_merged


def test_best_merged_prefers_snap_when_widget_omits_new_lines() -> None:
    import streamlit as st

    from views import gl_sheet_editor as gse

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
        ]
    )
    widget = baseline.copy()
    snap = pd.concat(
        [
            baseline,
            pd.DataFrame(
                [
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
                ]
            ),
        ],
        ignore_index=True,
    )
    scope = "save_snap_scope"
    cache_gen = 1
    snap_key = gse._merged_snap_key(cache_gen, scope)
    st.session_state[snap_key] = snap.to_dict(orient="records")
    try:
        out = _best_merged_for_save(
            widget,
            cache_gen=cache_gen,
            scope_id=scope,
            workbook_baseline=baseline,
        )
        assert len(out) == 3
        assert _plan_from_merged(baseline, out, include_tr=False, scope_id=scope).insert_rows
    finally:
        st.session_state.pop(snap_key, None)


def test_faux_del_alone_does_not_block_insert_plan_from_snap() -> None:
    import streamlit as st

    from views import gl_sheet_editor as gse

    baseline = pd.DataFrame(
        [
            {
                "_excel_row": 10,
                "After row": 0,
                "Account": "Cash",
                "Debit": 100.0,
                "Credit": 0.0,
                "Details": "a",
            },
            {
                "_excel_row": 12,
                "After row": 0,
                "Account": "Rent",
                "Debit": 0.0,
                "Credit": 50.0,
                "Details": "b",
            },
        ]
    )
    widget = baseline.copy()
    snap_rows = [
        baseline.iloc[0].to_dict(),
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
        baseline.iloc[1].to_dict(),
    ]
    scope = "faux_snap_scope"
    cache_gen = 2
    st.session_state[gse._faux_deleted_rows_key(scope)] = [11]
    st.session_state[gse._merged_snap_key(cache_gen, scope)] = snap_rows
    try:
        merged = _best_merged_for_save(
            widget,
            cache_gen=cache_gen,
            scope_id=scope,
            workbook_baseline=baseline,
        )
        plan = _plan_from_merged(baseline, merged, include_tr=False, scope_id=scope)
        assert len(plan.insert_rows) == 2
        assert 11 in plan.delete_rows
    finally:
        st.session_state.pop(gse._faux_deleted_rows_key(scope), None)
        st.session_state.pop(gse._merged_snap_key(cache_gen, scope), None)
