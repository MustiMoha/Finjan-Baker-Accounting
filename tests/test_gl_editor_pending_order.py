"""Pending GL editor grid must preserve inline new-row positions."""

from __future__ import annotations

import pandas as pd

import gl_editor as gled

from views.gl_sheet_editor import _apply_pending_over_baseline, _insert_compound_below_anchor


def test_apply_pending_keeps_new_row_below_anchor() -> None:
    baseline = pd.DataFrame(
        [
            {"_excel_row": 10, "After row": 0, "Account": "A"},
            {"_excel_row": 11, "After row": 0, "Account": "B"},
            {"_excel_row": 12, "After row": 0, "Account": "C"},
        ]
    )
    blank = gled.blank_editor_row(insert_after=10, include_tr=False)
    pending = _insert_compound_below_anchor(
        baseline.to_dict(orient="records"),
        insert_after=10,
        new_rows=[blank],
    )
    out = _apply_pending_over_baseline(baseline, pending)
    assert len(out) == 4
    assert int(out.iloc[0]["_excel_row"]) == 10
    assert int(out.iloc[1]["_excel_row"]) == 0
    assert int(out.iloc[1]["After row"]) == 10
    assert int(out.iloc[2]["_excel_row"]) == 11
