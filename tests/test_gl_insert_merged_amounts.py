"""Insert below rows whose credit leg merges account with debit/credit columns."""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
from openpyxl import Workbook

import excel_engine as ee
from views.gl_sheet_editor import (
    _editor_rows_from_compound_entry,
    _insert_compound_below_anchor,
    _plan_from_merged,
)


def test_insert_below_credit_leg_with_horizontal_account_amount_merge() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "gl.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "GL"
        ws.append(["Tr", "Date", "Details", "Account", "Debit", "Credit"])
        ws.append([1, date(2025, 1, 1), "Memo", "Cash", 100, 0])
        ws.append([None, None, "", "Rent Expense", 0, 100])
        ws.merge_cells(start_row=3, start_column=4, end_row=3, end_column=6)
        wb.save(path)
        wb.close()

        layout = {
            "mode": "manual",
            "header_first_row": 1,
            "data_start_row": 2,
            "columns": {
                "date": 1,
                "details": 2,
                "particulars": 3,
                "debit": 4,
                "credit": 5,
                "tr_number": 0,
            },
        }
        baseline = pd.DataFrame(
            [
                {
                    "_excel_row": 2,
                    "After row": 0,
                    "Date": "2025-01-01",
                    "Account": "Cash",
                    "Debit": 100.0,
                    "Credit": 0.0,
                    "Details": "Memo",
                    "Tr": "1",
                },
                {
                    "_excel_row": 3,
                    "After row": 0,
                    "Date": "",
                    "Account": "Rent Expense",
                    "Debit": 0.0,
                    "Credit": 100.0,
                    "Details": "",
                    "Tr": "",
                },
            ]
        )
        new_rows = _editor_rows_from_compound_entry(
            scope_id="merged_amt",
            insert_after=2,
            posting_date=date(2025, 1, 2),
            details="new",
            journal_lines=[
                {"account": "NewDr", "debit": "10.00", "credit": "0.00"},
                {"account": "NewCr", "debit": "0.00", "credit": "10.00"},
            ],
            include_tr=True,
        )
        merged = pd.DataFrame(
            _insert_compound_below_anchor(
                baseline.to_dict(orient="records"),
                insert_after=2,
                new_rows=new_rows,
                include_tr=True,
            )
        )
        plan = _plan_from_merged(baseline, merged, include_tr=True, scope_id="merged_amt")
        ee.apply_gl_edit_plan(path, plan, sheet_name="GL", layout=layout)

        rows = ee.read_gl_sheet_rows(path, sheet_name="GL", layout=layout, tail=0, keep_excel_row=True)
        by_er = {int(r["_excel_row"]): r for r in rows}
        assert by_er[2]["account"] == "Cash"
        assert by_er[3]["account"] == "Rent Expense"
        assert by_er[4]["account"] == "NewDr"
        assert by_er[5]["account"] == "NewCr"
