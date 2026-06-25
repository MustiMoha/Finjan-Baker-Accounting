"""GL editor guards: spurious widget zeros vs real text edits."""

from __future__ import annotations

import pandas as pd

from views.gl_sheet_editor import _grid_has_real_text_edits


def test_spurious_zeros_without_text_edit_not_real_edit() -> None:
    base = pd.DataFrame(
        [{"_excel_row": 10, "Account": "Cash", "Debit": 100.0, "Credit": 0.0, "Details": ""}]
    )
    patch = base.copy()
    patch.loc[0, "Debit"] = 0.0
    assert not _grid_has_real_text_edits(base, patch)


def test_text_edit_detected() -> None:
    base = pd.DataFrame(
        [{"_excel_row": 10, "Account": "Cash", "Debit": 100.0, "Credit": 0.0, "Details": ""}]
    )
    patch = base.copy()
    patch.loc[0, "Details"] = "updated"
    assert _grid_has_real_text_edits(base, patch)
