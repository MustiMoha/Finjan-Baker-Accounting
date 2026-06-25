"""Account bucket rule ordering and payable/expense safeguards."""

from __future__ import annotations

import account_buckets as ab


def test_expense_contains_fee_does_not_tag_legal_fees_payable_without_ap_rule() -> None:
    """Broad «fee» expense rule must not capture liability captions carrying «payable»."""
    maps = [{"kind": "expense", "text": "fee", "match": "contains"}]
    assert ab.match_bucket_kind("Legal fees payable (Saad Almansoury)", maps) is None


def test_longer_accounts_payable_pattern_wins_over_fee() -> None:
    maps = [
        {"kind": "expense", "text": "fee", "match": "contains"},
        {"kind": "accounts_payable", "text": "service fees", "match": "contains"},
    ]
    lab = "Service fees (NOUGA)"
    assert ab.match_bucket_kind(lab, maps) == "accounts_payable"


def test_mappings_sorted_longer_contains_first() -> None:
    ordered = ab.mappings_for_match_iterations(
        [
            {"kind": "expense", "text": "fee", "match": "contains"},
            {"kind": "expense", "text": "bank charges", "match": "contains"},
        ]
    )
    assert ordered[0]["text"] == "bank charges"


def test_bank_fee_still_maps_expense() -> None:
    maps = [{"kind": "expense", "text": "fee", "match": "contains"}]
    assert ab.match_bucket_kind("Bank fee", maps) == "expense"
