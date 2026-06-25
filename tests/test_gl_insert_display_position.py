"""Display list order when inserting below a mid-month anchor."""

from __future__ import annotations

from views.gl_sheet_editor import _insert_compound_below_anchor


def test_insert_not_placed_at_end_of_month_slice() -> None:
    records = [
        {
            "_excel_row": 10,
            "After row": 0,
            "Date": "2025-06-01",
            "Account": "Cash",
            "Debit": 1.0,
            "Credit": 0.0,
        },
        {
            "_excel_row": 11,
            "After row": 0,
            "Date": "",
            "Account": "Bank",
            "Debit": 0.0,
            "Credit": 1.0,
        },
        {
            "_excel_row": 12,
            "After row": 0,
            "Date": "2025-06-02",
            "Account": "Rent",
            "Debit": 2.0,
            "Credit": 0.0,
        },
        {
            "_excel_row": 200,
            "After row": 0,
            "Date": "2025-06-30",
            "Account": "MonthEnd",
            "Debit": 1.0,
            "Credit": 0.0,
        },
    ]
    new_rows = [
        {"_excel_row": 0, "After row": 10, "Account": "NewDr", "Debit": 5.0, "Credit": 0.0},
        {"_excel_row": 0, "After row": 10, "Account": "NewCr", "Debit": 0.0, "Credit": 5.0},
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
        "MonthEnd",
    ]
