"""Save must keep pending inserts when the data_editor widget drops Row # 0 lines."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from views.gl_sheet_editor import (
    _best_merged_for_save,
    _grid_has_pending_new_rows,
    _merged_snap_key,
    _pending_edits_key,
    _plan_from_merged,
    _safe_stash_pending_edits,
    _safe_write_merged_snap,
)


def test_best_merged_prefers_pending_over_widget_baseline_only() -> None:
    scope = "save_scope_pending"
    cache_gen = 7
    baseline = pd.DataFrame(
        [
            {
                "_excel_row": 10,
                "After row": 0,
                "Date": "2025-06-01",
                "Account": "Cash",
                "Debit": 1.0,
                "Credit": 0.0,
                "Details": "a",
            },
            {
                "_excel_row": 11,
                "After row": 0,
                "Date": "",
                "Account": "Bank",
                "Debit": 0.0,
                "Credit": 1.0,
                "Details": "",
            },
        ]
    )
    pending = baseline.to_dict(orient="records") + [
        {
            "_excel_row": 0,
            "After row": 11,
            "Date": "2025-06-02",
            "Account": "NewDr",
            "Debit": 5.0,
            "Credit": 0.0,
            "Details": "new",
        },
        {
            "_excel_row": 0,
            "After row": 11,
            "Date": "",
            "Account": "NewCr",
            "Debit": 0.0,
            "Credit": 5.0,
            "Details": "",
        },
    ]
    st.session_state[_pending_edits_key(scope)] = pending
    widget_only = baseline.copy()
    picked = _best_merged_for_save(
        widget_only,
        cache_gen=cache_gen,
        scope_id=scope,
        workbook_baseline=baseline,
    )
    assert _grid_has_pending_new_rows(picked)
    plan = _plan_from_merged(baseline, picked, include_tr=False, scope_id=scope)
    assert len(plan.insert_rows) == 2
    st.session_state.pop(_pending_edits_key(scope), None)


def test_safe_stash_does_not_wipe_pending_new_rows() -> None:
    scope = "save_scope_stash"
    baseline = pd.DataFrame(
        [
            {
                "_excel_row": 10,
                "After row": 0,
                "Account": "Cash",
                "Debit": 1.0,
                "Credit": 0.0,
            }
        ]
    )
    pending = baseline.to_dict(orient="records") + [
        {"_excel_row": 0, "After row": 10, "Account": "New", "Debit": 1.0, "Credit": 0.0},
    ]
    st.session_state[_pending_edits_key(scope)] = pending
    _safe_stash_pending_edits(scope, baseline.copy(), baseline=baseline)
    kept = st.session_state[_pending_edits_key(scope)]
    assert len(kept) == 2
    assert kept[1]["Account"] == "New"
    st.session_state.pop(_pending_edits_key(scope), None)


def test_safe_snap_keeps_prior_add_entry_snapshot() -> None:
    scope = "save_scope_snap"
    cache_gen = 3
    snap_key = _merged_snap_key(cache_gen, scope)
    good = [
        {"_excel_row": 10, "After row": 0, "Account": "Cash", "Debit": 1.0, "Credit": 0.0},
        {"_excel_row": 0, "After row": 10, "Account": "New", "Debit": 2.0, "Credit": 0.0},
    ]
    st.session_state[snap_key] = good
    _safe_write_merged_snap(
        cache_gen,
        scope,
        pd.DataFrame([good[0]]),
    )
    assert len(st.session_state[snap_key]) == 2
    st.session_state.pop(snap_key, None)
