"""Tests for GL spatial credit fragmentation and memo-row folding."""

from __future__ import annotations

import excel_engine as ee


def _row(tr: object, dt: object, account: object, debit: object, credit: object) -> tuple:
    """Build a worksheet row tuple (col0 = Tr#, col1 = date, col2 = account, D = debit, E = credit)."""
    r = ["", "", "", "", ""]
    r[0], r[1], r[2], r[3], r[4] = tr, dt, account, debit, credit
    return tuple(r)


def test_apply_spatial_credit_keeps_each_split_credit_account() -> None:
    """Previously all continuation credits collapsed onto the **last** account (wrong)."""
    colmap = ee.GlColumnMap(
        tr_number=0,
        date=1,
        particulars=2,
        debit=3,
        credit=4,
        details=1,
        data_start_row=1,
    )
    amt_col = colmap.debit + 1
    assert amt_col == colmap.credit

    matrix = [
        _row(1, "2025-06-25", "Cash", 100_000, 0),
        _row("", "2025-06-25", "Owners Equity ( Ali )", 0, 50_000),
        _row("", "2025-06-25", "Owners Equity ( Yousef)", 0, 50_000),
        _row("", "", "(50K Ali, 50K yousef)", 0.0, 0.0),
    ]
    records: list[dict] = [
        {
            "_excel_row": 1,
            "gl_date": "2025-06-25",
            "description": "",
            "account": "Cash",
            "debit": 100_000.0,
            "credit": 0.0,
            "currency_iso": "QAR",
            "original_currency": "QAR",
            "original_amount": 100_000.0,
            "transaction_number": 1,
        },
        {
            "_excel_row": 2,
            "gl_date": "2025-06-25",
            "description": "",
            "account": "Owners Equity ( Ali )",
            "debit": 0.0,
            "credit": 50_000.0,
            "currency_iso": "QAR",
        },
        {
            "_excel_row": 3,
            "gl_date": "2025-06-25",
            "description": "",
            "account": "Owners Equity ( Yousef)",
            "debit": 0.0,
            "credit": 50_000.0,
            "currency_iso": "QAR",
        },
        {
            "_excel_row": 4,
            "gl_date": "",
            "description": "",
            "account": "(50K Ali, 50K yousef)",
            "debit": 0.0,
            "credit": 0.0,
            "currency_iso": "QAR",
        },
    ]

    staged = ee.apply_spatial_credit_from_matrix(matrix, records, colmap)
    acc_amounts = {
        str(r["account"]): ee.row_amount(r.get("credit")) for r in staged if ee.row_amount(r.get("credit")) > 0.01
    }
    assert acc_amounts.get("Owners Equity ( Ali )", 0) == 50_000.0
    assert acc_amounts.get("Owners Equity ( Yousef)", 0) == 50_000.0
    assert acc_amounts.get("Cash", 0) == 0.0


def test_finalize_merge_memo_into_prior_line_description() -> None:
    staged = ee.apply_spatial_credit_from_matrix(
        [
            _row(1, "2025-06-25", "Cash", 100_000, 0),
            _row("", "2025-06-25", "Owners Equity ( Ali )", 0, 50_000),
            _row("", "2025-06-25", "Owners Equity ( Yousef)", 0, 50_000),
            _row("", "", "(50K Ali, 50K yousef)", 0.0, 0.0),
        ],
        [
            {
                "_excel_row": 1,
                "gl_date": "2025-06-25",
                "description": "",
                "account": "Cash",
                "debit": 100_000.0,
                "credit": 0.0,
                "currency_iso": "QAR",
                "original_currency": "QAR",
                "original_amount": 100_000.0,
            },
            {
                "_excel_row": 2,
                "gl_date": "2025-06-25",
                "description": "",
                "account": "Owners Equity ( Ali )",
                "debit": 0.0,
                "credit": 50_000.0,
                "currency_iso": "QAR",
            },
            {
                "_excel_row": 3,
                "gl_date": "2025-06-25",
                "description": "",
                "account": "Owners Equity ( Yousef)",
                "debit": 0.0,
                "credit": 50_000.0,
                "currency_iso": "QAR",
            },
            {
                "_excel_row": 4,
                "gl_date": "",
                "description": "",
                "account": "(50K Ali, 50K yousef)",
                "debit": 0.0,
                "credit": 0.0,
                "currency_iso": "QAR",
            },
        ],
        ee.GlColumnMap(tr_number=0, date=1, particulars=2, debit=3, credit=4, details=1),
    )

    finalized = ee.finalize_gl_records(staged, keep_excel_row=False)
    # Memo row folded away; narration appended onto the preceding GL line's description column.
    yousef = next(
        r for r in finalized if "Yousef" in str(r.get("account"))
    )
    assert "(50K Ali, 50K yousef)" in str(yousef.get("description") or "")


def test_finalize_keeps_zero_amount_rows_with_real_account() -> None:
    """Orphaned split-credit legs must not disappear after a parent row delete on reload."""
    staged = [
        {
            "_excel_row": 2,
            "gl_date": "2025-06-25",
            "description": "",
            "account": "Owners Equity ( Ali )",
            "debit": 0.0,
            "credit": 0.0,
            "currency_iso": "QAR",
        },
        {
            "_excel_row": 3,
            "gl_date": "2025-06-25",
            "description": "",
            "account": "Owners Equity ( Yousef)",
            "debit": 0.0,
            "credit": 0.0,
            "currency_iso": "QAR",
        },
    ]
    finalized = ee.finalize_gl_records(staged, keep_excel_row=True)
    accounts = {str(r.get("account")) for r in finalized}
    assert "Owners Equity ( Ali )" in accounts
    assert "Owners Equity ( Yousef)" in accounts
