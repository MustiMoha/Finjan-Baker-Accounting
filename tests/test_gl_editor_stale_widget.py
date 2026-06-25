"""Stale data_editor session state must not wipe pending edits or new rows."""

from __future__ import annotations

import pandas as pd

from views.gl_sheet_editor import (
    _merge_cell_edits_by_excel_row,
    _widget_overlay_is_stale,
)


def test_stale_widget_detected_when_row_count_drops() -> None:
    editor = pd.DataFrame(
        [
            {"_excel_row": 10, "Account": "Cash", "Debit": 1.0, "Credit": 0.0},
            {"_excel_row": 0, "After row": 10, "Account": "New", "Debit": 0.0, "Credit": 0.0},
        ]
    )
    widget = editor.iloc[:1].copy()
    assert _widget_overlay_is_stale(editor, widget)


def test_pending_new_row_kept_when_widget_drops_it() -> None:
    editor = pd.DataFrame(
        [
            {"_excel_row": 10, "After row": 0, "Account": "Cash", "Debit": 100.0, "Credit": 0.0},
            {
                "_excel_row": 0,
                "After row": 10,
                "Account": "New line",
                "Debit": 5.0,
                "Credit": 0.0,
                "Details": "memo",
            },
        ]
    )
    widget = editor.iloc[:1].copy()
    widget.loc[0, "Debit"] = 0.0
    widget.loc[0, "Credit"] = 0.0
    if _widget_overlay_is_stale(editor, widget):
        merged = editor
    else:
        merged = _merge_cell_edits_by_excel_row(editor, widget)
    assert len(merged) == 2
    assert merged.iloc[1]["Account"] == "New line"
    assert float(merged.iloc[1]["Debit"]) == 5.0


def test_two_new_rows_merge_by_queue() -> None:
    editor = pd.DataFrame(
        [
            {"_excel_row": 10, "After row": 0, "Account": "A", "Debit": 1.0, "Credit": 0.0},
            {"_excel_row": 0, "After row": 10, "Account": "N1", "Debit": 0.0, "Credit": 0.0},
            {"_excel_row": 0, "After row": 10, "Account": "N2", "Debit": 0.0, "Credit": 0.0},
        ]
    )
    patch = editor.copy()
    patch.loc[1, "Debit"] = 2.0
    out = _merge_cell_edits_by_excel_row(editor, patch)
    assert out.iloc[1]["Account"] == "N1"
    assert float(out.iloc[1]["Debit"]) == 2.0
    assert out.iloc[2]["Account"] == "N2"
