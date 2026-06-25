"""Expense breakdown chart labels."""

from __future__ import annotations

import pandas as pd

import account_buckets as ab
import financial_kpis as fkpi


def test_expense_breakdown_splits_by_account_not_generic_bucket() -> None:
    doc = ab.normalize_buckets_document(
        {
            "buckets": [
                {
                    "id": "b-exp",
                    "name": "Expenses",
                    "category": "expense",
                    "template_key": "expense",
                    "rollup": True,
                    "heuristic": False,
                }
            ],
            "mappings": [
                {"bucket_id": "b-exp", "text": "expense", "match": "contains", "field": "account"},
            ],
        }
    )
    df = pd.DataFrame(
        [
            {"account": "610 Rent expense", "debit": 1000.0, "credit": 0.0},
            {"account": "620 Salaries", "debit": 5000.0, "credit": 0.0},
            {"account": "630 Marketing expense", "debit": 800.0, "credit": 0.0},
        ]
    )
    rows = fkpi.revenue_expense_breakdown(
        df,
        debit_col="debit",
        credit_col="credit",
        bucket_doc=doc,
        kind="expense",
    )
    labels = {r["label"] for r in rows}
    assert "Expenses" not in labels
    assert "Rent expense" in labels
    assert "Salaries" in labels
    assert "Marketing expense" in labels


def test_expense_breakdown_merges_case_only_label_differences() -> None:
    df = pd.DataFrame(
        [
            {"account": "610 Supplies expense", "debit": 100.0, "credit": 0.0},
            {"account": "611 Supplies Expense", "debit": 50.0, "credit": 0.0},
        ]
    )
    rows = fkpi.revenue_expense_breakdown(
        df,
        debit_col="debit",
        credit_col="credit",
        bucket_doc=ab.default_buckets_document(),
        kind="expense",
    )
    assert len(rows) == 1
    assert rows[0]["amount"] == 150.0
    assert ab.fold_bucket_key(str(rows[0]["label"])) == ab.fold_bucket_key("Supplies Expense")


def test_expense_breakdown_uses_named_expense_bucket_when_specific() -> None:
    doc = ab.default_buckets_document()
    df = pd.DataFrame(
        [
            {"account": "Payroll salaries", "debit": 4000.0, "credit": 0.0},
        ]
    )
    rows = fkpi.revenue_expense_breakdown(
        df,
        debit_col="debit",
        credit_col="credit",
        bucket_doc=doc,
        kind="expense",
    )
    assert len(rows) == 1
    assert rows[0]["label"] == "Salaries expense"
