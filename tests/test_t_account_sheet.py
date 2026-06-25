"""Spatial T-account sheet parsing (Finjan-style Beg Balance blocks)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import account_buckets as ab
import excel_engine as ee
import gl_analytics as gla
from openpyxl import Workbook

import t_account_sheet as tas


def _write_finjan_workbook(path: str, opening: float) -> None:
    wb = Workbook()
    gl = wb.active
    gl.title = "Journal"
    gl.append(["Journal Entries Template", "", "", "", "", "", "", ""])
    gl.append(["Date", "#", "Accounts", "", "Debit", "Credit", "", "Evidenced"])
    gl.append(["15-Jan", "1", "Cash", "", "1000", "", "", "y"])
    gl.append(["", "", "", "Owner's Equity ( Abdulla )", "", "1000", "", "y"])

    tac = wb.create_sheet("T-accounts")
    tac["A1"] = "Cash"
    tac["A2"] = "Date"
    tac["D2"] = "Date"
    tac["A3"] = "31-Dec"
    tac["B3"] = 2
    tac["C3"] = f"QAR {opening:,.2f} Beg Balance"
    tac["A4"] = "15-Jan"
    tac["B4"] = 5
    tac["C4"] = "QAR 15,000"

    tac["F1"] = "Owner's Equity ( Abdulla )"
    tac["F2"] = "Date"
    tac["I2"] = "Date"
    tac["G3"] = "31-Dec"
    tac["I3"] = f"QAR 34,000 Beg Balance"

    wb.save(path)
    wb.close()


def test_parse_cash_beg_balance_block() -> None:
    opening = 6167.13
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = f.name
    try:
        _write_finjan_workbook(path, opening)
        blocks = tas.parse_t_account_sheet_blocks(path, "T-accounts", default_year=2026)
        cash_blocks = [b for b in blocks if "cash" in b.account.casefold()]
        assert len(cash_blocks) == 1
        block = cash_blocks[0]
        opening_lines = [ln for ln in block.lines if ln.get("is_opening")]
        assert len(opening_lines) == 1
        assert abs(float(opening_lines[0]["amount"]) - opening) < 0.02
        assert opening_lines[0]["side"] == "debit"
    finally:
        Path(path).unlink(missing_ok=True)


def test_t_account_opening_merged_into_journal_read() -> None:
    opening = 6167.13
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        path = f.name
    try:
        _write_finjan_workbook(path, opening)
        records = ee.read_gl_sheet_rows(
            path,
            sheet_name="Journal",
            tail=0,
        )
        records = ee.enrich_gl_records_with_tac_openings(
            records,
            path,
            gl_sheet_name="Journal",
            t_accounts_sheet_name="T-accounts",
            default_year=2026,
        )
        cash_open = [
            r
            for r in records
            if str(r.get("account")).strip().casefold() == "cash"
            and gla.is_opening_or_brought_forward_rec(r)
        ]
        assert len(cash_open) == 1
        assert abs(ee.row_amount(cash_open[0]["debit"]) - opening) < 0.02
        df = ee.gl_flat_records_activity_dataframe(records, fiscal_start_month=1)
        tb = gla.trial_balance(df, bucket_doc=ab.default_buckets_document())
        cash = tb[tb["account"].astype(str).str.contains("Cash", case=False, na=False)]
        assert abs(float(cash.iloc[0]["opening_balance"]) - opening) < 0.02
        assert abs(float(cash.iloc[0]["net_balance"]) - (1000.0 + opening)) < 0.02
    finally:
        Path(path).unlink(missing_ok=True)


def test_infer_t_accounts_sheet_name() -> None:
    names = ["Journal", "T-accounts", "Notes"]
    assert tas.infer_t_accounts_sheet_name(names, "Journal") == "T-accounts"
