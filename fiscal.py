"""Fiscal period helpers using a configurable fiscal-year start month (1–12)."""

from __future__ import annotations

import calendar
from datetime import date
from typing import NamedTuple


class FiscalPeriod(NamedTuple):
    fiscal_year: int
    fiscal_period: int  # 1–12 within that fiscal year


def fiscal_period_for(d: date, start_month: int) -> FiscalPeriod:
    """
    Fiscal year starts in `start_month` (1=Jan ... 12=Dec).
    Example: start_month=4 → FY2024 runs Apr 1 2024 – Mar 31 2025, period 1 = April.
    """
    sm = int(start_month)
    if sm < 1 or sm > 12:
        raise ValueError("start_month must be 1–12")

    # First month of current fiscal year
    if d.month >= sm:
        fy_start_year = d.year
    else:
        fy_start_year = d.year - 1

    # 1-based period index within fiscal year
    months_from_start = (d.year - fy_start_year) * 12 + (d.month - sm)
    fiscal_period = months_from_start + 1

    # Label fiscal year by calendar year containing FY start (common convention)
    fiscal_year_label = fy_start_year
    return FiscalPeriod(fiscal_year=fiscal_year_label, fiscal_period=fiscal_period)


def end_of_fiscal_year(start_month: int, fiscal_year_label: int) -> date:
    """Last calendar day of the fiscal year that begins in `fiscal_year_label`."""
    sm = int(start_month)
    end_month = sm - 1 if sm > 1 else 12
    end_year = fiscal_year_label if sm > 1 else fiscal_year_label + 1
    last_day = calendar.monthrange(end_year, end_month)[1]
    return date(end_year, end_month, last_day)


def calendar_month_for_fiscal_period(
    fiscal_year: int,
    fiscal_period: int,
    fiscal_start_month: int,
) -> tuple[int, int]:
    """
    Calendar (year, month) for fiscal period index.
    FY period 1 is the month containing `fiscal_start_month` in `fiscal_year`.
    """
    sm = int(fiscal_start_month)
    if sm < 1 or sm > 12:
        raise ValueError("fiscal_start_month must be 1–12")
    fp = int(fiscal_period)
    idx = fp - 1  # offset from FY start (0-based)
    total_from_jan_fy_year = sm - 1 + idx
    cal_month = (total_from_jan_fy_year % 12) + 1
    cal_year = int(fiscal_year) + total_from_jan_fy_year // 12
    return cal_year, cal_month


def fiscal_period_calendar_label(
    fiscal_year: int,
    fiscal_period: int,
    fiscal_start_month: int,
    *,
    long_month: bool = False,
) -> str:
    """Human label e.g. 'Apr 2024' for the calendar month of that fiscal period."""
    y, m = calendar_month_for_fiscal_period(fiscal_year, fiscal_period, fiscal_start_month)
    name = calendar.month_name[m] if long_month else calendar.month_abbr[m]
    return f"{name} {y}"
