"""Default posting date for Add GL entry from Financials scope."""

from __future__ import annotations

from datetime import date

from views.gl_sheet_editor import default_posting_date_for_gl_scope


def test_default_date_latest_fiscal_month_in_filter() -> None:
    fp_lookup = {
        "Jun 2025": (2025, 6),
        "Jul 2025": (2025, 7),
    }
    got = default_posting_date_for_gl_scope(
        [],
        pick_months=["Jun 2025", "Jul 2025"],
        fp_lookup=fp_lookup,
        fiscal_start_month=1,
    )
    assert got == date(2025, 7, 1)


def test_default_date_from_slice_when_no_month_filter() -> None:
    slice_raw = [
        {"gl_date": "2025-05-15"},
        {"gl_date": "2025-08-03"},
    ]
    got = default_posting_date_for_gl_scope(
        slice_raw,
        pick_months=[],
        fp_lookup={},
        fiscal_start_month=1,
    )
    assert got == date(2025, 8, 1)
