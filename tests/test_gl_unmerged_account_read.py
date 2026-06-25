"""Read account labels from unmerged / spillover cells on the GL sheet."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from openpyxl import Workbook

import excel_engine as ee


def test_read_account_from_unmerged_column_right_of_particulars() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "gl.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "GL"
        ws.append(["Date", "Details", "Particulars", "Account", "Debit", "Credit"])
        ws.append([date(2025, 6, 1), "Pay", None, "Utilities", 0.0, 125.50])
        wb.save(path)
        wb.close()

        layout = {
            "mode": "manual",
            "header_first_row": 1,
            "data_start_row": 2,
            "columns": {
                "date": 0,
                "details": 1,
                "particulars": 2,
                "debit": 4,
                "credit": 5,
            },
        }
        rows = ee.read_gl_sheet_rows(path, sheet_name="GL", layout=layout, tail=0)
        assert len(rows) == 1
        assert rows[0]["account"] == "Utilities"


def test_read_account_from_unmerged_cell_left_of_particulars() -> None:
    """Account label sits one column left of the mapped particulars column (unmerged)."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "gl.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "GL"
        ws.append(["Date", "Ledger", "Particulars", "Debit", "Credit"])
        ws.append([date(2025, 6, 1), "Petty cash", None, 10.0, 0.0])
        wb.save(path)
        wb.close()

        layout = {
            "mode": "manual",
            "header_first_row": 1,
            "data_start_row": 2,
            "columns": {
                "date": 0,
                "details": 1,
                "particulars": 2,
                "debit": 3,
                "credit": 4,
            },
        }
        rows = ee.read_gl_sheet_rows(path, sheet_name="GL", layout=layout, tail=0)
        assert len(rows) == 1
        assert rows[0]["account"] == "Petty cash"
