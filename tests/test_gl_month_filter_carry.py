"""Fiscal month filter must keep continuation lines that inherit a date."""

from __future__ import annotations

from datetime import date

import fiscal

from views.financials import _filter_raw_records_by_months


def test_month_filter_keeps_continuation_row_after_dated_header() -> None:
    records = [
        {"gl_date": date(2025, 6, 1), "account": "Cash"},
        {"gl_date": None, "account": "Bank"},
        {"gl_date": date(2025, 7, 1), "account": "Rent"},
    ]
    fy_m = 7
    fp = fiscal.fiscal_period_for(date(2025, 6, 15), fy_m)
    lab = fiscal.fiscal_period_calendar_label(fp.fiscal_year, fp.fiscal_period, fy_m)
    fp_lookup = {lab: (fp.fiscal_year, fp.fiscal_period)}
    pick = [lab]
    out = _filter_raw_records_by_months(records, fy_m, fp_lookup, pick)
    assert [r["account"] for r in out] == ["Cash", "Bank"]
