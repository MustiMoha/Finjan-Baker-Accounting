"""Openpyxl-first workbook editing (row insert/delete with merged-cell safety)."""

from workbook_editor.merge_ops import delete_sheet_row, insert_sheet_rows, merged_ranges_on_row

__all__ = ["delete_sheet_row", "insert_sheet_rows", "merged_ranges_on_row"]
