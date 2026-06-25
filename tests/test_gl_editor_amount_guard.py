"""GL editor: preserve Debit/Credit when Streamlit data_editor returns spurious zeros."""

from __future__ import annotations

import pandas as pd

from views import gl_sheet_editor as gse


def test_merge_patch_keeps_baseline_when_widget_zeros_both_amounts() -> None:
    base = {
        "_excel_row": 10,
        "Date": "2025-01-01",
        "Account": "Cash",
        "Debit": 100.0,
        "Credit": 0.0,
        "Details": "pay",
    }
    patch = dict(base)
    patch["Debit"] = 0.0
    patch["Credit"] = 0.0
    patch["Details"] = "pay updated"
    out = gse._merge_patch_into_row(base, patch, list(base.keys()))
    assert float(out["Debit"]) == 100.0
    assert float(out["Credit"]) == 0.0
    assert out["Details"] == "pay updated"


def test_merge_patch_keeps_baseline_for_single_zeroed_amount_column() -> None:
    base = {
        "_excel_row": 11,
        "Date": "2025-01-02",
        "Account": "Rent",
        "Debit": 0.0,
        "Credit": 50.0,
        "Details": "rent",
    }
    patch = dict(base)
    patch["Debit"] = 0.0
    patch["Credit"] = 0.0
    out = gse._merge_patch_into_row(base, patch, list(base.keys()))
    assert float(out["Credit"]) == 50.0


def test_merge_patch_applies_intentional_amount_change() -> None:
    base = {
        "_excel_row": 12,
        "Date": "2025-01-03",
        "Account": "Fees",
        "Debit": 10.0,
        "Credit": 0.0,
        "Details": "fee",
    }
    patch = dict(base)
    patch["Debit"] = 25.0
    out = gse._merge_patch_into_row(base, patch, list(base.keys()))
    assert float(out["Debit"]) == 25.0


def test_repair_pending_restores_per_column_zeros() -> None:
    baseline = pd.DataFrame(
        [
            {
                "_excel_row": 20,
                "Date": "2025-02-01",
                "Account": "Cash",
                "Debit": 200.0,
                "Credit": 0.0,
                "Details": "x",
            }
        ]
    )
    pending = [
        {
            "_excel_row": 20,
            "Date": "2025-02-01",
            "Account": "Cash",
            "Debit": 0.0,
            "Credit": 0.0,
            "Details": "x",
        }
    ]
    fixed = gse._repair_pending_amounts(baseline, pending)
    assert float(fixed[0]["Debit"]) == 200.0


def test_repair_pending_restores_blank_account_when_amounts_glitch() -> None:
    baseline = pd.DataFrame(
        [
            {
                "_excel_row": 21,
                "Account": "Owners Equity",
                "Debit": 50.0,
                "Credit": 0.0,
                "Details": "memo",
            }
        ]
    )
    pending = [
        {
            "_excel_row": 21,
            "Account": "",
            "Debit": 0.0,
            "Credit": 0.0,
            "Details": "",
        }
    ]
    fixed = gse._repair_pending_amounts(baseline, pending)
    assert fixed[0]["Account"] == "Owners Equity"
    assert float(fixed[0]["Debit"]) == 50.0


def test_widget_spurious_zero_detection() -> None:
    base = pd.DataFrame(
        [
            {
                "_excel_row": 30,
                "Date": "2025-03-01",
                "Account": "A",
                "Debit": 75.0,
                "Credit": 0.0,
                "Details": "",
            }
        ]
    )
    widget = base.copy()
    widget.loc[0, "Debit"] = 0.0
    assert gse._widget_amounts_spuriously_zeroed(base, widget)
