"""Tests for invoice text helpers (no PDF fixtures required)."""

from __future__ import annotations

from datetime import date

import invoice_extract as invx


def test_parse_money_tokens_basic():
    text = "Subtotal $1,234.56 Tax 12.00 Total $1500.00"
    nums = invx.parse_money_tokens(text)
    assert nums
    assert max(nums) >= 1500


def test_parse_dates_iso_like():
    text = "Issued 2024-03-15 due 03/20/2024"
    ds = invx.parse_dates(text)
    assert date(2024, 3, 15) in ds


def test_guess_currency_iso():
    assert invx.guess_currency_iso("Amount due EUR 120") == "EUR"


def test_extract_from_plain_text_structure():
    blob = "Acme Supplies\nInvoice INV-2024-009\nDate 2025-01-10\nTotal Due $250.00 USD\n"
    ext = invx.extract_from_plain_text(blob, method="test")
    assert ext["source"]["method"] == "test"
    assert ext.get("total") == 250.0


def test_draft_journal_balanced_amounts():
    ext = {
        "line_items": [{"description": "Widget", "line_total": 100.0}],
        "total": 100.0,
        "source": {},
        "warnings": [],
    }
    lines = invx.draft_journal_lines_from_extraction(ext)
    assert len(lines) >= 2
    deb = sum(float(x["debit"]) for x in lines)
    cred = sum(float(x["credit"]) for x in lines)
    assert abs(deb - cred) < 0.01
