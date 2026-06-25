"""Provisional Row # while editing; coherent projection on save."""

from __future__ import annotations

import pandas as pd

from views.gl_sheet_editor import (
    _apply_display_row_numbers,
    _dataframe_for_grid_display,
    _editor_rows_from_compound_entry,
    _project_coherent_row_numbers_on_save,
)


def test_display_row_numbers_for_pending_insert() -> None:
    records = [
        {"_excel_row": 10, "After row": 0, "Account": "Cash"},
        {"_excel_row": 11, "After row": 0, "Account": "Bank"},
        {"_excel_row": -1, "After row": 11, "Account": "NewDr"},
        {"_excel_row": -2, "After row": 11, "Account": "NewCr"},
        {"_excel_row": 24, "After row": 0, "Account": "Rent"},
    ]
    out = _apply_display_row_numbers(records)
    assert [r["row_num"] for r in out] == [10, 11, 12, 13, 24]


def test_coherent_row_numbers_on_save_shift_workbook_rows() -> None:
    records = [
        {"_excel_row": 10, "After row": 0, "Account": "Cash"},
        {"_excel_row": 11, "After row": 0, "Account": "Bank"},
        {"_excel_row": -1, "After row": 11, "Account": "NewDr"},
        {"_excel_row": -2, "After row": 11, "Account": "NewCr"},
        {"_excel_row": 24, "After row": 0, "Account": "Rent"},
    ]
    out = _project_coherent_row_numbers_on_save(records, faux_deleted=set())
    assert [r["row_num"] for r in out] == [10, 11, 12, 13, 26]


def test_dataframe_for_grid_display_adds_row_num_column() -> None:
    df = pd.DataFrame(
        [
            {"_excel_row": 5, "After row": 0, "Account": "A"},
            {"_excel_row": -1, "After row": 5, "Account": "B"},
        ]
    )
    shown = _dataframe_for_grid_display(df)
    assert "row_num" in shown.columns
    assert int(shown.iloc[0]["row_num"]) == 5
    assert int(shown.iloc[1]["row_num"]) == 6


def test_new_compound_lines_get_negative_ids() -> None:
    from datetime import date

    rows = _editor_rows_from_compound_entry(
        scope_id="row_num_test",
        insert_after=8,
        posting_date=date(2025, 6, 1),
        details="x",
        journal_lines=[
            {"account": "Dr", "debit": "1", "credit": "0"},
            {"account": "Cr", "debit": "0", "credit": "1"},
        ],
        include_tr=False,
    )
    assert len(rows) == 2
    assert all(int(r["_excel_row"]) < 1 for r in rows)
    numbered = _apply_display_row_numbers(
        [{"_excel_row": 8, "After row": 0}] + rows
    )
    assert numbered[1]["row_num"] == 9
    assert numbered[2]["row_num"] == 10
