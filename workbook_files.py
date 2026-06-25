"""MIME types for workbook uploads (Supabase Storage content-type headers)."""

from __future__ import annotations

from pathlib import Path


def mime_type_for_filename(filename: str) -> str:
    suf = Path(filename).suffix.lower()
    if suf == ".xlsm":
        return "application/vnd.ms-excel.sheet.macroEnabled.12"
    if suf == ".xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if suf == ".xls":
        return "application/vnd.ms-excel"
    if suf == ".csv":
        return "text/csv"
    if suf == ".pdf":
        return "application/pdf"
    if suf in (".png",):
        return "image/png"
    if suf in (".jpg", ".jpeg"):
        return "image/jpeg"
    if suf == ".webp":
        return "image/webp"
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
