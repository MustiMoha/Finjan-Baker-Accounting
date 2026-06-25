"""Line-level bucket rules (field=any vs account)."""

from __future__ import annotations

import account_buckets as ab


def _doc_with_rule(*, text: str, category: str, field: str) -> dict:
    bid = "b1"
    return {
        "buckets": [
            {
                "id": bid,
                "name": "Payroll bucket",
                "category": category,
                "template_key": "",
                "rollup": True,
                "heuristic": False,
            }
        ],
        "mappings": [{"bucket_id": bid, "text": text, "match": "contains", "field": field}],
    }


def test_any_field_matches_description_not_account() -> None:
    doc = _doc_with_rule(text="payroll", category="expense", field="any")
    ctx = ab.coerce_context(doc)
    haystack = ab.fold_line_haystack("Misc clearing", "January payroll run", "", "")
    hit = ab.match_account_to_bucket("Misc clearing", ctx, line_haystack=haystack)
    assert hit is not None
    assert hit.category == "expense"


def test_account_field_ignores_description() -> None:
    doc = _doc_with_rule(text="payroll", category="expense", field="account")
    ctx = ab.coerce_context(doc)
    haystack = ab.fold_line_haystack("Misc clearing", "January payroll run", "", "")
    hit = ab.match_account_to_bucket("Misc clearing", ctx, line_haystack=haystack)
    assert hit is None
