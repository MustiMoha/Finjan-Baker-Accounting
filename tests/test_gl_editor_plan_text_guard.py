"""Save plan must not treat blank widget text as intentional clears."""

from __future__ import annotations

import pandas as pd

import gl_editor as gled


def test_plan_ignores_blank_account_from_widget() -> None:
    baseline = pd.DataFrame(
        [
            {
                "_excel_row": 10,
                "After row": 0,
                "Date": "2025-01-01",
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
    edited = baseline.copy()
    edited.at[1, "Account"] = ""
    edited.at[1, "Details"] = ""
    plan = gled.plan_from_editor_diff(baseline, edited, include_tr=False)
    assert plan.updates == []
