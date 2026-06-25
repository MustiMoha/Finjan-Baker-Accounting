"""Grid display order for pending inserts (Row # 0 must not sort above workbook rows)."""

from __future__ import annotations

from views.gl_sheet_editor import _canonicalize_editor_display_order


def test_canonicalize_puts_pending_lines_below_anchor_not_at_top() -> None:
    shuffled = [
        {"_excel_row": 0, "After row": 10, "Account": "NewDr", "Debit": 5.0, "Credit": 0.0},
        {"_excel_row": 0, "After row": 10, "Account": "NewCr", "Debit": 0.0, "Credit": 5.0},
        {"_excel_row": 10, "After row": 0, "Account": "Cash", "Debit": 1.0, "Credit": 0.0},
        {"_excel_row": 11, "After row": 0, "Account": "Bank", "Debit": 0.0, "Credit": 1.0},
    ]
    out = _canonicalize_editor_display_order(shuffled, include_tr=False)
    assert [r["Account"] for r in out] == ["Cash", "Bank", "NewDr", "NewCr"]
