"""Heuristic classify_account / fold_account_key behaviour for Albaker-style ledgers."""

import account_buckets as ab
import gl_analytics as gla


def test_fold_account_key_equity_spacing() -> None:
    a = ab.fold_account_key("Owners Equity ( Yousef)")
    b = ab.fold_account_key("Owners Equity ( yousef )")
    assert a == b


def test_classify_accounts_payable_shorthand() -> None:
    assert gla.classify_account("A/P Yousef", None) == "Liability"
    assert gla.classify_account("A/P ( Nouga)", None) == "Liability"


def test_classify_broker_commission_expense() -> None:
    assert gla.classify_account("broker commission", None) == "Expense"


def test_classify_office_furniture_asset() -> None:
    assert gla.classify_account("Office & furniture", None) == "Asset"


def test_classify_bank_fee_not_asset() -> None:
    assert gla.classify_account("Bank fee", None) == "Expense"


def test_classify_plain_bank_asset() -> None:
    assert gla.classify_account("Bank deposit account", None) == "Asset"


def test_interest_revenue_before_fee_expense() -> None:
    assert gla.classify_account("Interest revenue", None) == "Revenue"


def test_service_fees_operating_expense() -> None:
    assert gla.classify_account("Service fees (NOUGA)", None) == "Expense"


def test_accounts_receivable_shorthand_asset() -> None:
    assert gla.classify_account("A/R (IBRAHIM QASSIM)", None) == "Asset"


def test_accounts_receivable_typo_recivable_asset() -> None:
    assert gla.classify_account("Legal fees Recivable", None) == "Asset"


def test_service_rev_abbrev_revenue() -> None:
    assert gla.classify_account("Service Rev", None) == "Revenue"


def test_service_revenue_in_name() -> None:
    assert gla.classify_account("service revenue (Saad Almansoury)", None) == "Revenue"
