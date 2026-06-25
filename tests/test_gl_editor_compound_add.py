"""Compound GL add-entry helpers (insert below anchor)."""

from __future__ import annotations

from datetime import date

import pandas as pd

import gl_editor as gled
from views.gl_sheet_editor import (
    _editor_rows_from_compound_entry,
    _excel_row_int,
    _first_new_row_display_index,
    _insert_compound_below_anchor,
)


def test_insert_compound_preserves_line_order() -> None:
    baseline = [
        {"_excel_row": 10, "After row": 0, "Account": "A"},
        {"_excel_row": 12, "After row": 0, "Account": "C"},
    ]
    lines = _editor_rows_from_compound_entry(
        scope_id="test_compound",
        insert_after=10,
        posting_date=date(2025, 6, 1),
        details="compound",
        journal_lines=[
            {"account": "Cash", "debit": "100.00", "credit": "0.00"},
            {"account": "Fees", "debit": "0.00", "credit": "100.00"},
        ],
        include_tr=False,
    )
    out = _insert_compound_below_anchor(baseline, insert_after=10, new_rows=lines)
    assert [r["Account"] for r in out] == ["A", "Cash", "Fees", "C"]
    assert all(_excel_row_int(r.get("_excel_row")) < 1 for r in out[1:3])
    assert all(_excel_row_int(r.get("After row")) == 10 for r in out[1:3])
    assert lines[0]["Date"] == "2025-06-01"
    assert lines[1]["Date"] == ""
    assert lines[0]["Details"] == "compound"
    assert lines[1]["Details"] == ""


def test_plan_compound_insert_two_lines_same_anchor() -> None:
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
    new_rows = _editor_rows_from_compound_entry(
        scope_id="test_plan",
        insert_after=10,
        posting_date=date(2025, 1, 2),
        details="mid",
        journal_lines=[
            {"account": "Mid1", "debit": "5.00", "credit": "0.00"},
            {"account": "Mid2", "debit": "0.00", "credit": "5.00"},
        ],
        include_tr=False,
    )
    edited_recs = _insert_compound_below_anchor(
        baseline.to_dict(orient="records"),
        insert_after=10,
        new_rows=new_rows,
    )
    edited = pd.DataFrame(edited_recs)
    plan = gled.plan_from_editor_diff(baseline, edited, include_tr=False)
    assert len(plan.insert_rows) == 2
    assert plan.insert_rows[0]["insert_after"] == 10
    assert plan.insert_rows[1]["insert_after"] == 10
    assert plan.insert_rows[0]["account"] == "Mid1"
    assert plan.insert_rows[1]["account"] == "Mid2"


def test_first_new_row_display_index() -> None:
    recs = [
        {"_excel_row": 10, "After row": 0},
        {"_excel_row": 0, "After row": 10},
        {"_excel_row": 0, "After row": 10},
    ]
    assert _first_new_row_display_index(recs, 10) == 1
