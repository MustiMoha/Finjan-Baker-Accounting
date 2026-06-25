"""Trial balance roll-up for shared dashboard buckets (A/P, A/R, salaries, equity, service revenue)."""

from __future__ import annotations

import pandas as pd

import account_buckets as ab
import gl_analytics as gla


def _tb(df: pd.DataFrame, maps: list | None = None) -> pd.DataFrame:
    return gla.trial_balance(df, bucket_mappings=maps)


def test_trade_ap_rollup_multiple_captions() -> None:
    df = pd.DataFrame(
        [
            {"account": "A/P Yousef", "debit": 0.0, "credit": 100.0},
            {"account": "Accounts Payable - Vendor X", "debit": 0.0, "credit": 50.0},
            {"account": "210 Accounts payable (nouga)", "debit": 10.0, "credit": 0.0},
        ]
    )
    tb = _tb(df)
    assert len(tb) == 1
    assert tb.iloc[0]["account"] == gla.TRADE_AP_LABEL
    assert float(tb.iloc[0]["credits"]) == 150.0
    assert float(tb.iloc[0]["debits"]) == 10.0


def test_trade_ar_rollup_multiple_captions() -> None:
    df = pd.DataFrame(
        [
            {"account": "A/R (IBRAHIM QASSIM)", "debit": 200.0, "credit": 0.0},
            {"account": "Accounts Receivable - Client", "debit": 75.0, "credit": 0.0},
        ]
    )
    tb = _tb(df)
    assert len(tb) == 1
    assert tb.iloc[0]["account"] == gla.TRADE_AR_LABEL
    assert float(tb.iloc[0]["debits"]) == 275.0


def test_settings_accounts_payable_kind_single_bucket() -> None:
    df = pd.DataFrame(
        [
            {"account": "Vendor A trade", "debit": 0.0, "credit": 40.0},
            {"account": "Vendor B trade", "debit": 0.0, "credit": 60.0},
        ]
    )
    maps = [
        {"kind": "accounts_payable", "text": "vendor a", "match": "contains"},
        {"kind": "accounts_payable", "text": "vendor b", "match": "contains"},
    ]
    tb = _tb(df, maps)
    assert len(tb) == 1
    assert tb.iloc[0]["account"] == gla.TRADE_AP_LABEL
    assert float(tb.iloc[0]["credits"]) == 100.0


def test_t_account_lines_bucket_includes_all_sub_accounts() -> None:
    df = pd.DataFrame(
        [
            {
                "account": "A/P Yousef",
                "gl_date": "2025-01-01",
                "description": "inv",
                "debit": 0.0,
                "credit": 30.0,
            },
            {
                "account": "Accounts Payable - Nouga",
                "gl_date": "2025-01-02",
                "description": "bill",
                "debit": 0.0,
                "credit": 20.0,
            },
        ]
    )
    lines = gla.t_account_lines(df, gla.TRADE_AP_LABEL, bucket_doc=ab.default_buckets_document())
    assert len(lines) == 2
    assert set(lines["account"].astype(str)) == {"A/P Yousef", "Accounts Payable - Nouga"}


def test_salaries_expense_rollup() -> None:
    df = pd.DataFrame(
        [
            {"account": "Salaries - NOUGA", "debit": 1000.0, "credit": 0.0},
            {"account": "Salary expense (admin)", "debit": 500.0, "credit": 0.0},
            {"account": "Office rent", "debit": 200.0, "credit": 0.0},
        ]
    )
    tb = _tb(df)
    assert len(tb) == 2
    sal = tb[tb["account"] == gla.ROLLUP_SALARIES_LABEL]
    assert len(sal) == 1
    assert float(sal.iloc[0]["debits"]) == 1500.0


def test_owners_equity_partner_lines_not_rolled_together() -> None:
    df = pd.DataFrame(
        [
            {"account": "Owners Equity ( Yousef)", "debit": 0.0, "credit": 100.0},
            {"account": "Owners Equity (Yousef )", "debit": 0.0, "credit": 50.0},
            {"account": "Retained earnings", "debit": 0.0, "credit": 200.0},
        ]
    )
    tb = _tb(df)
    assert len(tb) == 2
    oe = tb[tb["account"].astype(str).str.contains("yousef", case=False, na=False)]
    assert len(oe) == 1
    assert float(oe.iloc[0]["credits"]) == 150.0


def test_service_revenue_rollup() -> None:
    df = pd.DataFrame(
        [
            {"account": "Service Rev", "debit": 0.0, "credit": 80.0},
            {"account": "service revenue (Saad Almansoury)", "debit": 0.0, "credit": 120.0},
            {"account": "Interest revenue", "debit": 0.0, "credit": 40.0},
        ]
    )
    tb = _tb(df)
    assert len(tb) == 2
    sr = tb[tb["account"] == gla.ROLLUP_SERVICE_REVENUE_LABEL]
    assert len(sr) == 1
    assert float(sr.iloc[0]["credits"]) == 200.0


def test_settings_service_revenue_kind_single_bucket() -> None:
    df = pd.DataFrame(
        [
            {"account": "Consulting line A", "debit": 0.0, "credit": 10.0},
            {"account": "Consulting line B", "debit": 0.0, "credit": 20.0},
        ]
    )
    maps = [
        {"kind": "service_revenue", "text": "consulting line a", "match": "contains"},
        {"kind": "service_revenue", "text": "consulting line b", "match": "contains"},
    ]
    tb = _tb(df, maps)
    assert len(tb) == 1
    assert tb.iloc[0]["account"] == gla.ROLLUP_SERVICE_REVENUE_LABEL


def test_rollup_buckets_split_from_trade_ap() -> None:
    df = pd.DataFrame(
        [
            {"account": "A/P Vendor", "debit": 0.0, "credit": 10.0},
            {"account": "Legal fees payable", "debit": 0.0, "credit": 20.0},
            {"account": "Cheques payable", "debit": 0.0, "credit": 30.0},
        ]
    )
    tb = _tb(df)
    assert len(tb) == 3
    assert set(tb["account"].tolist()) == {
        gla.TRADE_AP_LABEL,
        gla.ROLLUP_LEGAL_FEES_PAYABLE_LABEL,
        gla.ROLLUP_CHEQUES_PAYABLE_LABEL,
    }


def test_bank_fees_technology_cash_equipment_rollup() -> None:
    df = pd.DataFrame(
        [
            {"account": "Bank fee", "debit": 5.0, "credit": 0.0},
            {"account": "Bank fees (NOUGA)", "debit": 3.0, "credit": 0.0},
            {"account": "Technology expense", "debit": 100.0, "credit": 0.0},
            {"account": "Tech supplies", "debit": 40.0, "credit": 0.0},
            {"account": "100 Cash", "debit": 500.0, "credit": 0.0},
            {"account": "Petty cash", "debit": 50.0, "credit": 0.0},
            {"account": "Office equipment", "debit": 200.0, "credit": 0.0},
            {"account": "Equipment - vehicles", "debit": 800.0, "credit": 0.0},
        ]
    )
    tb = _tb(df)
    assert len(tb) == 4
    assert float(tb.loc[tb["account"] == gla.ROLLUP_BANK_FEES_LABEL, "debits"].iloc[0]) == 8.0
    assert float(tb.loc[tb["account"] == gla.ROLLUP_TECHNOLOGY_EXPENSE_LABEL, "debits"].iloc[0]) == 140.0
    assert float(tb.loc[tb["account"] == gla.ROLLUP_CASH_LABEL, "debits"].iloc[0]) == 550.0
    assert float(tb.loc[tb["account"] == gla.ROLLUP_EQUIPMENT_LABEL, "debits"].iloc[0]) == 1000.0


def test_custom_bucket_name_and_category() -> None:
    doc = {
        "buckets": [
            {
                "id": "b-custom",
                "name": "Qatar vendor pool",
                "category": "liability",
                "template_key": "",
                "rollup": True,
                "heuristic": False,
            }
        ],
        "mappings": [
            {"bucket_id": "b-custom", "text": "vendor qatar", "match": "contains"},
            {"bucket_id": "b-custom", "text": "vendor doha", "match": "contains"},
        ],
    }
    df = pd.DataFrame(
        [
            {"account": "A/P vendor qatar", "debit": 0.0, "credit": 10.0},
            {"account": "A/P vendor doha", "debit": 0.0, "credit": 20.0},
        ]
    )
    tb = gla.trial_balance(df, bucket_mappings=doc)
    assert len(tb) == 1
    assert tb.iloc[0]["account"] == "Qatar vendor pool"
    assert float(tb.iloc[0]["credits"]) == 30.0
    assert gla.classify_account("A/P vendor qatar", doc) == "Liability"


def test_trial_balance_groups_duplicate_bucket_names_case_insensitive() -> None:
    """Even before normalize merges ids, rolled-up TB rows use case-insensitive bucket keys."""
    doc = {
        "buckets": [
            {
                "id": "b1",
                "name": "Supplies Expense",
                "category": "expense",
                "template_key": "",
                "rollup": True,
                "heuristic": False,
            },
            {
                "id": "b2",
                "name": "supplies expense",
                "category": "expense",
                "template_key": "",
                "rollup": True,
                "heuristic": False,
            },
        ],
        "mappings": [
            {"bucket_id": "b1", "text": "paper stock", "match": "contains", "field": "account"},
            {"bucket_id": "b2", "text": "ink toner", "match": "contains", "field": "account"},
        ],
    }
    df = pd.DataFrame(
        [
            {"account": "Paper stock", "debit": 80.0, "credit": 0.0},
            {"account": "Ink toner", "debit": 20.0, "credit": 0.0},
        ]
    )
    tb = gla.trial_balance(df, bucket_mappings=doc)
    expense_rows = tb[tb["account"].astype(str).str.casefold().str.contains("supplies")]
    assert len(expense_rows) == 1
    assert float(expense_rows.iloc[0]["debits"]) == 100.0


def test_bucket_names_case_insensitive_merge() -> None:
    doc = {
        "buckets": [
            {
                "id": "b1",
                "name": "legal fees",
                "category": "liability",
                "template_key": "",
                "rollup": True,
                "heuristic": False,
            },
            {
                "id": "b2",
                "name": "Legal Fees",
                "category": "liability",
                "template_key": "",
                "rollup": True,
                "heuristic": False,
            },
        ],
        "mappings": [
            {"bucket_id": "b1", "text": "legal fee vendor a", "match": "contains"},
            {"bucket_id": "b2", "text": "legal fee vendor b", "match": "contains"},
        ],
    }
    norm = ab.normalize_buckets_document(doc)
    assert len(norm["buckets"]) == 1
    assert len({m["bucket_id"] for m in norm["mappings"]}) == 1
    df = pd.DataFrame(
        [
            {"account": "Legal fee vendor a", "debit": 0.0, "credit": 10.0},
            {"account": "legal fee vendor b", "debit": 0.0, "credit": 20.0},
        ]
    )
    tb = gla.trial_balance(df, bucket_mappings=norm)
    assert len(tb) == 1
    mask = gla.trial_balance_group_mask(df, "legal fees", bucket_doc=norm)
    assert int(mask.sum()) == 2
    mask2 = gla.trial_balance_group_mask(df, "Legal Fees", bucket_doc=norm)
    assert int(mask2.sum()) == 2


def test_trial_balance_period_opening_and_closing() -> None:
    df = pd.DataFrame(
        [
            {
                "account": "Cash",
                "fiscal_year": 2025,
                "fiscal_period": 1,
                "debit": 100.0,
                "credit": 0.0,
            },
            {
                "account": "Cash",
                "fiscal_year": 2025,
                "fiscal_period": 2,
                "debit": 0.0,
                "credit": 30.0,
            },
        ]
    )
    tb_all = gla.trial_balance(df, fiscal_start_month=1)
    assert float(tb_all.iloc[0]["net_balance"]) == 70.0

    tb_p2 = gla.trial_balance(
        df,
        fiscal_periods={(2025, 2)},
        fiscal_start_month=1,
    )
    row = tb_p2.iloc[0]
    assert float(row["opening_balance"]) == 100.0
    assert float(row["debits"]) == 0.0
    assert float(row["credits"]) == 30.0
    assert float(row["net_balance"]) == 70.0


def test_t_account_lines_beginning_balance_row() -> None:
    df = pd.DataFrame(
        [
            {
                "account": "Cash",
                "gl_date": "2025-01-15",
                "description": "deposit",
                "fiscal_year": 2025,
                "fiscal_period": 1,
                "debit": 100.0,
                "credit": 0.0,
            },
            {
                "account": "Cash",
                "gl_date": "2025-02-10",
                "description": "payment",
                "fiscal_year": 2025,
                "fiscal_period": 2,
                "debit": 0.0,
                "credit": 30.0,
            },
        ]
    )
    lines = gla.t_account_lines(
        df,
        "Cash",
        fiscal_periods={(2025, 2)},
        fiscal_start_month=1,
    )
    assert len(lines) == 2
    assert lines.iloc[0]["description"] == gla.BEGINNING_BALANCE_LABEL
    assert float(lines.iloc[0]["balance"]) == 100.0
    assert float(lines.iloc[1]["balance"]) == 70.0
