"""GL editor merge must keep new rows and text when Streamlit glitches amounts."""

from __future__ import annotations

import pandas as pd

from views.gl_sheet_editor import (
    _merge_cell_edits_by_excel_row,
    _merge_patch_into_row,
)


def test_merge_appends_new_row_when_widget_has_extra_line() -> None:
    base = pd.DataFrame(
        [
            {"_excel_row": 10, "Account": "Cash", "Debit": 100.0, "Credit": 0.0},
            {"_excel_row": 11, "Account": "Rent", "Debit": 0.0, "Credit": 50.0},
        ]
    )
    patch = pd.DataFrame(
        [
            {"_excel_row": 10, "Account": "Cash", "Debit": 0.0, "Credit": 0.0},
            {"_excel_row": 0, "After row": 10, "Account": "", "Debit": 0.0, "Credit": 0.0},
            {"_excel_row": 11, "Account": "Rent", "Debit": 0.0, "Credit": 0.0},
        ]
    )
    out = _merge_cell_edits_by_excel_row(base, patch)
    assert len(out) == 3
    assert float(out.iloc[0]["Debit"]) == 100.0
    assert int(out.iloc[2]["_excel_row"]) < 1
    assert int(out.iloc[2]["After row"]) == 11
    assert int(out.iloc[1]["_excel_row"]) == 11
    assert float(out.iloc[1]["Credit"]) == 50.0
    assert out.iloc[1]["Account"] == "Rent"


def test_merge_extra_row_keeps_base_order_and_amounts() -> None:
    base = pd.DataFrame(
        [
            {"_excel_row": 10, "After row": 0, "Account": "Cash", "Debit": 100.0, "Credit": 0.0},
            {"_excel_row": 11, "After row": 0, "Account": "Rent", "Debit": 0.0, "Credit": 50.0},
        ]
    )
    patch = pd.DataFrame(
        [
            {"_excel_row": 10, "Account": "Cash", "Debit": 0.0, "Credit": 0.0},
            {"_excel_row": 0, "After row": 10, "Account": "", "Debit": 0.0, "Credit": 0.0},
            {"_excel_row": 11, "Account": "Rent", "Debit": 0.0, "Credit": 0.0},
        ]
    )
    out = _merge_cell_edits_by_excel_row(base, patch)
    assert len(out) == 3
    assert int(out.iloc[0]["_excel_row"]) == 10
    assert float(out.iloc[0]["Debit"]) == 100.0
    assert int(out.iloc[2]["_excel_row"]) < 1
    assert int(out.iloc[2]["After row"]) == 11
    assert int(out.iloc[1]["_excel_row"]) == 11
    assert float(out.iloc[1]["Credit"]) == 50.0


def test_merge_keeps_account_when_amounts_spuriously_zeroed() -> None:
    base = {
        "_excel_row": 10,
        "Account": "Owners Equity",
        "Debit": 50.0,
        "Credit": 0.0,
        "Details": "memo",
    }
    patch = {"Account": "", "Debit": 0.0, "Credit": 0.0, "Details": ""}
    cols = ["Account", "Debit", "Credit", "Details"]
    row = _merge_patch_into_row(base, patch, cols)
    assert row["Account"] == "Owners Equity"
    assert float(row["Debit"]) == 50.0
