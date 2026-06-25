"""Date-only editor fields and GL display-order validation."""

from __future__ import annotations

from datetime import date, datetime

import gl_editor as gled
from views.gl_sheet_editor import (
    _canonicalize_editor_display_order,
    _finalize_editor_records_or_error,
    _insert_compound_below_anchor,
)


def test_format_gl_date_strips_time() -> None:
    assert gled.format_gl_date_for_editor(datetime(2025, 6, 3, 14, 30)) == "2025-06-03"
    assert gled.format_gl_date_for_editor("2025-06-03 00:00:00") == "2025-06-03"
    assert gled.format_gl_date_for_editor(date(2025, 1, 15)) == "2025-01-15"


def test_posting_date_from_anchor_row() -> None:
    records = [
        {"_excel_row": 10, "Date": "2025-06-01", "Account": "Cash"},
        {"_excel_row": 11, "Date": "", "Account": "Bank"},
    ]
    got = gled.posting_date_for_editor_anchor(
        records, 10, default=date(2020, 1, 1), include_tr=False
    )
    assert got == date(2025, 6, 1)
    got_credit = gled.posting_date_for_editor_anchor(
        records, 11, default=date(2020, 1, 1), include_tr=False
    )
    assert got_credit == date(2025, 6, 1)


def test_validate_rejects_workbook_rows_out_of_order() -> None:
    records = [
        {"_excel_row": 12, "After row": 0, "Account": "B"},
        {"_excel_row": 10, "After row": 0, "Account": "A"},
    ]
    err = gled.validate_gl_editor_display_order(records)
    assert err is not None
    assert "out of order" in err.lower()


def test_validate_rejects_pending_not_below_anchor() -> None:
    records = [
        {"_excel_row": 10, "After row": 0, "Account": "Cash"},
        {"_excel_row": 12, "After row": 0, "Account": "Rent"},
        {"_excel_row": 0, "After row": 10, "Account": "NewDr"},
    ]
    err = gled.validate_gl_editor_display_order(records)
    assert err is not None
    assert "below row 10" in err.lower() or "grouped" in err.lower()


def test_finalize_repairs_shuffled_pending() -> None:
    shuffled = [
        {"_excel_row": 0, "After row": 10, "Account": "NewDr", "Debit": 5.0, "Credit": 0.0},
        {"_excel_row": 0, "After row": 10, "Account": "NewCr", "Debit": 0.0, "Credit": 5.0},
        {"_excel_row": 10, "After row": 0, "Account": "Cash", "Debit": 1.0, "Credit": 0.0},
        {"_excel_row": 11, "After row": 0, "Account": "Bank", "Debit": 0.0, "Credit": 1.0},
    ]
    canon, err = _finalize_editor_records_or_error(shuffled, scope_id="ord_test", include_tr=False)
    assert err is None
    assert canon is not None
    assert [r["Account"] for r in canon] == ["Cash", "Bank", "NewDr", "NewCr"]


def test_add_insert_uses_block_end_not_between_debit_credit() -> None:
    records = [
        {"_excel_row": 10, "Date": "2025-06-01", "Account": "Cash", "Debit": 1.0, "Credit": 0.0},
        {"_excel_row": 11, "Date": "", "Account": "Bank", "Debit": 0.0, "Credit": 1.0},
        {"_excel_row": 12, "Date": "2025-06-02", "Account": "Rent", "Debit": 2.0, "Credit": 0.0},
    ]
    new_rows = [
        {"_excel_row": -1, "After row": 11, "Account": "NewDr", "Debit": 5.0, "Credit": 0.0},
        {"_excel_row": -2, "After row": 11, "Account": "NewCr", "Debit": 0.0, "Credit": 5.0},
    ]
    out = _insert_compound_below_anchor(
        records,
        insert_after=10,
        new_rows=new_rows,
        include_tr=False,
    )
    assert [r["Account"] for r in out] == [
        "Cash",
        "Bank",
        "NewDr",
        "NewCr",
        "Rent",
    ]
