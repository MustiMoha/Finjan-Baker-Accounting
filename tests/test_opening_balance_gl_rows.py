"""Opening-balance rows above the journal band (Finjan-style brought-forward cash)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import account_buckets as ab
import excel_engine as ee
import gl_analytics as gla


def _finjan_matrix_with_opening_cash(opening_debit: float) -> list[tuple]:
    raw = [
        ["", "", "Cash", "", f"QAR {opening_debit:,.2f} Beg Balance", "", "", ""],
        ["Journal Entries Template", "", "", "", "", "", "", ""],
        ["Date", "#", "Accounts", "", "Debit", "Credit", "", "Evidenced"],
        ["15-Jan", "1", "Cash", "", "1000", "", "", "y"],
        ["", "", "", "Owner's Equity ( Abdulla )", "", "1000", "", "y"],
    ]
    width = 8
    return [tuple((list(r) + [None] * width)[:width]) for r in raw]


def test_extract_opening_balance_cash_above_journal_band() -> None:
    opening = 6167.13
    matrix = _finjan_matrix_with_opening_cash(opening)
    colmap = ee.resolve_gl_column_map(matrix, None)
    rows = ee.extract_opening_balance_gl_rows(matrix, colmap)
    assert len(rows) == 1
    assert rows[0]["account"] == "Cash"
    assert ee.row_amount(rows[0]["debit"]) == opening
    assert rows[0].get("opening_balance") is True


def test_opening_cash_included_in_trial_balance_and_activity_df() -> None:
    opening = 6167.13
    matrix = _finjan_matrix_with_opening_cash(opening)
    colmap = ee.resolve_gl_column_map(matrix, None)
    opening_rows = ee.extract_opening_balance_gl_rows(matrix, colmap)
    ds = max(0, colmap.data_start_row - 1)
    buf: list[dict] = []
    header_skip = [False]
    for offset, row in enumerate(matrix[ds:]):
        rec = ee._row_tuple_to_record_dynamic(
            row, colmap, header_skipped_ref=header_skip, excel_row_1based=ds + offset + 1
        )
        if rec:
            buf.append(rec)
    records = ee.finalize_gl_records(opening_rows + buf, keep_excel_row=True)
    df = ee.gl_flat_records_activity_dataframe(records, fiscal_start_month=1)
    doc = ab.default_buckets_document()
    tb = gla.trial_balance(df, bucket_doc=doc)
    cash = tb[tb["account"].astype(str).str.contains("Cash", case=False, na=False)]
    assert len(cash) == 1
    row = cash.iloc[0]
    # journal cash 1000 + opening 6167.13
    assert abs(float(row["net_balance"]) - (1000.0 + opening)) < 0.02
    assert abs(float(row["opening_balance"]) - opening) < 0.02
    assert abs(float(row["debits"]) - 1000.0) < 0.02
    assert row.get("opening_label") in (gla.BEGINNING_BALANCE_LABEL, gla.BROUGHT_FORWARD_LABEL)


def test_brought_forward_cash_in_journal_band() -> None:
    opening = 6167.13
    raw = [
        ["Journal Entries Template", "", "", "", "", "", "", ""],
        ["Date", "#", "Accounts", "", "Debit", "Credit", "", "Evidenced"],
        ["15-Jan", "1", "Cash brought forward", "", f"{opening:.2f}", "", "", "y"],
        ["15-Jan", "2", "Cash", "", "1000", "", "", "y"],
        ["", "", "", "Owner's Equity ( Abdulla )", "", "1000", "", "y"],
    ]
    width = 8
    matrix = [tuple((list(r) + [None] * width)[:width]) for r in raw]
    colmap = ee.resolve_gl_column_map(matrix, None)
    ds = max(0, colmap.data_start_row - 1)
    buf: list[dict] = []
    header_skip = [False]
    for offset, row in enumerate(matrix[ds:]):
        rec = ee._row_tuple_to_record_dynamic(
            row, colmap, header_skipped_ref=header_skip, excel_row_1based=ds + offset + 1
        )
        if rec:
            buf.append(rec)
    records = ee.finalize_gl_records(buf, keep_excel_row=True)
    cash_bf = [r for r in records if str(r.get("account")).strip().casefold() == "cash" and r.get("brought_forward")]
    assert len(cash_bf) == 1
    assert ee.row_amount(cash_bf[0]["debit"]) == opening
    df = ee.gl_flat_records_activity_dataframe(records, fiscal_start_month=1)
    ledger = gla.t_account_lines(df, "Cash", bucket_doc=ab.default_buckets_document())
    bf_lines = ledger[ledger["description"].astype(str) == gla.BROUGHT_FORWARD_LABEL]
    assert len(bf_lines) == 1
    assert abs(float(bf_lines.iloc[0]["debit"]) - opening) < 0.02
    tb = gla.trial_balance(df, bucket_doc=ab.default_buckets_document())
    cash = tb[tb["account"].astype(str).str.contains("Cash", case=False, na=False)]
    assert abs(float(cash.iloc[0]["opening_balance"]) - opening) < 0.02
    assert abs(float(cash.iloc[0]["net_balance"]) - (1000.0 + opening)) < 0.02


def test_read_gl_csv_with_opening_row() -> None:
    import csv as csv_mod

    opening = 6167.13
    rows = [
        ["", "", "Cash", "", f"QAR {opening:,.2f} Beg Balance", "", "", ""],
        ["Journal Entries Template", "", "", "", "", "", "", ""],
        ["Date", "#", "Accounts", "", "Debit", "Credit", "", "Evidenced"],
        ["15-Jan", "1", "Cash", "", "1000", "", "", "y"],
        ["", "", "", "Owners Equity ( Abdulla )", "", "1000", "", "y"],
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8") as f:
        csv_mod.writer(f).writerows(rows)
        path = f.name
    try:
        records = ee.read_gl_csv_rows(path, tail=0, keep_excel_row=True)
        cash_recs = [r for r in records if str(r.get("account")).strip().lower() == "cash"]
        assert any(r.get("opening_balance") for r in cash_recs)
        net = sum(ee.row_amount(r.get("debit")) - ee.row_amount(r.get("credit")) for r in cash_recs)
        assert abs(net - (1000.0 + opening)) < 0.02
    finally:
        Path(path).unlink(missing_ok=True)
