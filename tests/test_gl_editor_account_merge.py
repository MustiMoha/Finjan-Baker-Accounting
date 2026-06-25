"""Grid merge must not blank indented credit-leg account labels."""

from __future__ import annotations

import pandas as pd

from views.gl_sheet_editor import _merge_cell_edits_by_excel_row


def test_merge_keeps_account_when_widget_returns_blank() -> None:
    editor = pd.DataFrame(
        [
            {
                "_excel_row": 10,
                "After row": 0,
                "Date": "2025-06-01",
                "Account": "Cash",
                "Debit": 100.0,
                "Credit": 0.0,
                "Details": "memo",
            },
            {
                "_excel_row": 11,
                "After row": 0,
                "Date": "",
                "Account": "Equity",
                "Debit": 0.0,
                "Credit": 100.0,
                "Details": "",
            },
        ]
    )
    edited = editor.copy()
    edited.at[1, "Account"] = ""
    merged = _merge_cell_edits_by_excel_row(editor, edited)
    assert str(merged.iloc[1]["Account"]).strip() == "Equity"
