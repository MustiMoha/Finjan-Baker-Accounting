"""Exclude repeated journal column-header rows from parsed GL."""

from __future__ import annotations

from pathlib import Path

import excel_engine as ee


def test_is_non_posting_gl_row_repeat_accounts_header() -> None:
    row = {
        "gl_date": ":",
        "account": "Accounts",
        "description": "Accounts",
        "debit": 0.0,
        "credit": 0.0,
        "transaction_number": "#",
    }
    assert ee.is_non_posting_gl_row(row) is True


def test_is_non_posting_gl_row_real_zero_balance_kept() -> None:
    row = {
        "gl_date": "2025-07-01",
        "account": "Cash",
        "description": "",
        "debit": 0.0,
        "credit": 0.0,
    }
    assert ee.is_non_posting_gl_row(row) is False


def test_albaker_csv_has_no_accounts_header_lines() -> None:
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "Ali Albaker Accounting records For the year ended December 31.csv"
    if not csv_path.is_file():
        return
    rows = ee.read_gl_csv_rows(str(csv_path), tail=0)
    bad = [
        r
        for r in rows
        if ee._normalize_headerish_label(str(r.get("account") or "")) == "accounts"
        and ee.row_amount(r.get("debit")) <= 0.015
        and ee.row_amount(r.get("credit")) <= 0.015
    ]
    assert bad == []
