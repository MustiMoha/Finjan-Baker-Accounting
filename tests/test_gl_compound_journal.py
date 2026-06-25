"""Compound journal blocks (multi-debit / single-credit) and workbook balance checks."""

from __future__ import annotations

from pathlib import Path

import excel_engine as ee


def _row(tr: object, dt: object, account: object, debit: object, credit: object) -> tuple:
    r = ["", "", "", "", ""]
    r[0], r[1], r[2], r[3], r[4] = tr, dt, account, debit, credit
    return tuple(r)


def _colmap() -> ee.GlColumnMap:
    return ee.GlColumnMap(
        tr_number=0,
        date=1,
        particulars=2,
        debit=3,
        credit=4,
        details=1,
        data_start_row=1,
    )


def _totals(records: list[dict]) -> tuple[float, float]:
    d = sum(ee.row_amount(r.get("debit")) for r in records)
    c = sum(ee.row_amount(r.get("credit")) for r in records)
    return d, c


def test_journal_block_balanced_multi_debit_single_credit() -> None:
    """Entry 29-style: several debits, one cash credit — block ties before spatial runs."""
    records = [
        {
            "_excel_row": 1,
            "transaction_number": 29,
            "gl_date": "2025-08-10",
            "account": "Cheques Payable-RENT",
            "debit": 3458.0,
            "credit": 0.0,
        },
        {
            "_excel_row": 2,
            "account": "Equipment (TV)",
            "debit": 2859.0,
            "credit": 0.0,
        },
        {
            "_excel_row": 3,
            "account": "Office & furniture",
            "debit": 3650.0,
            "credit": 0.0,
        },
        {"_excel_row": 4, "account": "legal fees", "debit": 150.0, "credit": 0.0},
        {"_excel_row": 5, "account": "bank fee", "debit": 2.0, "credit": 0.0},
        {"_excel_row": 6, "account": "Cash", "debit": 0.0, "credit": 10119.0},
    ]
    blocks = ee.partition_journal_blocks(records)
    assert len(blocks) == 1
    assert ee.journal_block_balanced(blocks[0])


def test_spatial_skips_balanced_compound_block() -> None:
    """Spatial credit must not peel credits off a balanced multi-debit entry."""
    colmap = _colmap()
    matrix = [
        _row(29, "10-Aug", "Cheques Payable-RENT", "QAR 3,458", ""),
        _row("", "", "Equipment (TV)", "QAR 2,859", ""),
        _row("", "", "Office & furniture", "QAR 3,650", ""),
        _row("", "", "legal fees", "QAR 150", ""),
        _row("", "", "bank fee", "QAR 2", ""),
        _row("", "", "Cash", "", "QAR 10,119"),
    ]
    records = []
    for i in range(len(matrix)):
        deb_v, _ = ee.parse_money_cell(matrix[i][3])
        cre_v, _ = ee.parse_money_cell(matrix[i][4])
        records.append(
            {
                "_excel_row": i + 1,
                "transaction_number": 29 if i == 0 else None,
                "gl_date": "2025-08-10",
                "account": str(matrix[i][2]),
                "debit": float(deb_v or 0),
                "credit": float(cre_v or 0),
                "currency_iso": "QAR",
            }
        )
    staged = ee.apply_spatial_credit_from_matrix(matrix, records, colmap)
    deb, cre = _totals(staged)
    assert abs(deb - cre) < 0.02
    cash = next(r for r in staged if str(r.get("account")) == "Cash")
    assert ee.row_amount(cash.get("credit")) == 10119.0


def test_normalize_skips_debit_pair_flip_in_compound_journal() -> None:
    """Cash + A/R debits with Unearned credit below must not flip A/R into a credit leg."""
    records = [
        {
            "_excel_row": 53,
            "transaction_number": 12,
            "gl_date": "2026-02-25",
            "account": "Cash",
            "debit": 6000.0,
            "credit": 0.0,
        },
        {
            "_excel_row": 54,
            "account": "A/R",
            "debit": 6000.0,
            "credit": 0.0,
        },
        {
            "_excel_row": 55,
            "account": "Unearned Membership Revenue (AHMED ABOUSHAWISH)",
            "debit": 0.0,
            "credit": 12000.0,
        },
    ]
    out = ee.finalize_gl_records(records, keep_excel_row=True)
    ar = next(r for r in out if str(r.get("account")) == "A/R")
    assert ee.row_amount(ar.get("debit")) == 6000.0
    assert ee.row_amount(ar.get("credit")) == 0.0


def test_normalize_skips_adjacent_salary_debits_when_block_has_cash_credit() -> None:
    records = [
        {
            "_excel_row": 24,
            "transaction_number": 7,
            "gl_date": "2026-01-29",
            "account": "Salaries expense (Ahmed)",
            "debit": 4000.0,
            "credit": 0.0,
        },
        {
            "_excel_row": 25,
            "account": "Salaries expense (Aya)",
            "debit": 4000.0,
            "credit": 0.0,
        },
        {"_excel_row": 28, "account": "Cash", "debit": 0.0, "credit": 11284.0},
    ]
    out = ee.finalize_gl_records(records, keep_excel_row=True)
    aya = next(r for r in out if "Aya" in str(r.get("account")))
    assert ee.row_amount(aya.get("debit")) == 4000.0
    assert ee.row_amount(aya.get("credit")) == 0.0


def test_albaker_csv_import_debits_equal_credits() -> None:
    """Full Albaker CSV: parsed GL debits should equal credits after finalize."""
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "Ali Albaker Accounting records For the year ended December 31.csv"
    if not csv_path.is_file():
        return
    rows = ee.read_gl_csv_rows(str(csv_path), tail=0, keep_excel_row=True)
    deb, cre = _totals(rows)
    assert deb > 1000.0 and cre > 1000.0
    assert abs(deb - cre) < 1.0, f"debits={deb:,.2f} credits={cre:,.2f} gap={deb - cre:,.2f}"


def test_balance_sheet_snapshot_includes_period_net() -> None:
    import financial_kpis as fkpi

    cat = {
        "assets_net": 100.0,
        "liabilities_net": 40.0,
        "equity_net": 10.0,
        "total_revenue": 80.0,
        "total_expenses": 30.0,
    }
    snap = fkpi.balance_sheet_snapshot(cat, __import__("pandas").DataFrame(), debit_col="debit", credit_col="credit")
    assert snap["ale_balanced"] is True
    assert abs(float(snap["ale_difference"])) < 0.02
