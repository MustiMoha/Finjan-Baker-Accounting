"""Transaction numbers must be Arrow-safe (no mixed int/str columns)."""

from __future__ import annotations

import pandas as pd

import gl_editor as gled


def test_normalize_editor_tr_column_mixed_types() -> None:
    df = pd.DataFrame(
        [
            {"_excel_row": 10, "After row": 0, "Tr": 42, "Account": "A", "Debit": 1.0, "Credit": 0.0},
            {
                "_excel_row": 11,
                "After row": 0,
                "Tr": "testing insert/delete",
                "Account": "B",
                "Debit": 0.0,
                "Credit": 1.0,
            },
        ]
    )
    out = gled.normalize_editor_dataframe_dtypes(df, include_tr=True)
    assert all(isinstance(x, str) for x in out["Tr"])
    assert out.iloc[0]["Tr"] == "42"
    assert out.iloc[1]["Tr"] == "testing insert/delete"


def test_normalize_gl_records_for_display() -> None:
    raw = [
        {"transaction_number": 7, "account": "Cash"},
        {"transaction_number": "testing insert/delete", "account": "Fees"},
    ]
    out = gled.normalize_gl_records_for_display(raw)
    assert out[0]["transaction_number"] == "7"
    assert out[1]["transaction_number"] == "testing insert/delete"
