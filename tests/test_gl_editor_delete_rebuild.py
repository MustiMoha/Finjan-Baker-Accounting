"""Pending grid rebuild after faux delete must not resurrect cleared rows."""

from __future__ import annotations

import pandas as pd

from views.gl_sheet_editor import _apply_pending_over_baseline, _rebuild_pending_after_delete


def test_rebuild_pending_drops_deleted_and_keeps_new_lines() -> None:
    baseline = pd.DataFrame(
        [
            {"_excel_row": 10, "After row": 0, "Account": "A", "Debit": 1.0, "Credit": 0.0},
            {"_excel_row": 12, "After row": 0, "Account": "C", "Debit": 3.0, "Credit": 0.0},
        ]
    )
    pending_key = "fin_gl_pending_test_scope"
    import streamlit as st

    st.session_state[pending_key] = [
        {"_excel_row": 10, "After row": 0, "Account": "A edited", "Debit": 9.0, "Credit": 0.0},
        {"_excel_row": 0, "After row": 10, "Account": "New1", "Debit": 5.0, "Credit": 0.0},
        {"_excel_row": 0, "After row": 10, "Account": "New2", "Debit": 0.0, "Credit": 5.0},
        {"_excel_row": 11, "After row": 0, "Account": "Gone", "Debit": 2.0, "Credit": 0.0},
    ]

    # Monkeypatch pending key helper by calling rebuild with scope_id that uses our key
    # _rebuild_pending_after_delete uses _pending_edits_key(scope_id)
    from views import gl_sheet_editor as gse

    orig = gse._pending_edits_key
    gse._pending_edits_key = lambda _sid: pending_key
    try:
        out = _rebuild_pending_after_delete(
            "test_scope",
            baseline,
            {11},
            include_tr=False,
        )
    finally:
        gse._pending_edits_key = orig

    accounts = [str(r.get("Account") or "") for r in out.to_dict(orient="records")]
    assert "Gone" not in accounts
    assert accounts == ["A edited", "New1", "New2", "C"]
    st.session_state.pop(pending_key, None)


def test_partial_overlay_no_longer_restores_deleted_row() -> None:
    baseline = pd.DataFrame(
        [
            {"_excel_row": 10, "After row": 0, "Account": "A"},
            {"_excel_row": 11, "After row": 0, "Account": "B"},
        ]
    )
    pending = [{"_excel_row": 10, "After row": 0, "Account": "A edited"}]
    out = _apply_pending_over_baseline(baseline, pending)
    assert list(out["Account"]) == ["A edited", "B"]
