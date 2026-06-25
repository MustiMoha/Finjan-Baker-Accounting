"""Trial balance checks against Finjan Accounting 2026 journal CSV."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

import account_buckets as ab
import excel_engine as ee
import gl_analytics as gla


def _finjan_df() -> pd.DataFrame:
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "Finjan Accounting 2026.csv"
    if not csv_path.is_file():
        return pd.DataFrame()
    rows = ee.read_gl_csv_rows(str(csv_path), tail=0, keep_excel_row=True)
    return pd.DataFrame(rows)


def _tb_net(tb: pd.DataFrame, account_substr: str) -> float:
    hit = tb[tb["account"].astype(str).str.contains(account_substr, case=False, na=False)]
    if hit.empty:
        return 0.0
    return float(hit.iloc[0]["net_balance"])


def test_finjan_csv_debits_equal_credits() -> None:
    df = _finjan_df()
    if df.empty:
        return
    deb = float(df["debit"].sum())
    cre = float(df["credit"].sum())
    assert abs(deb - cre) < 1.0, f"debits={deb:,.2f} credits={cre:,.2f}"


def test_finjan_trial_balance_key_accounts() -> None:
    df = _finjan_df()
    if df.empty:
        return
    doc = ab.default_buckets_document()
    tb = gla.trial_balance(df, bucket_doc=doc)
    assert abs(_tb_net(tb, "receivable")) == 600.0
    assert abs(_tb_net(tb, "Salaries expense")) == 54100.0
    assert abs(_tb_net(tb, "Unearned Membership")) - 77000.0 < 1.0
    assert abs(_tb_net(tb, "Service revenue")) - 191370.4 < 0.1
    assert abs(_tb_net(tb, "Membership revenue")) - 47000.0 < 1.0


def test_trial_balance_for_display_category_order() -> None:
    df = pd.DataFrame(
        [
            {"account": "Rent expense", "debit": 100.0, "credit": 0.0},
            {"account": "Cash", "debit": 500.0, "credit": 0.0},
            {"account": "Service revenue", "debit": 0.0, "credit": 200.0},
        ]
    )
    tb = gla.trial_balance(df, bucket_doc=ab.default_buckets_document())
    disp = gla.trial_balance_for_display(tb, bucket_doc=ab.default_buckets_document())
    cats = disp["category"].astype(str).tolist()
    assert cats.index("Asset") < cats.index("Revenue")
    assert cats.index("Revenue") < cats.index("Expense")
    cash_row = disp[disp["account"].astype(str).str.contains("Cash", case=False, na=False)].iloc[0]
    assert float(cash_row["debits"]) == 500.0
    assert float(cash_row["credits"]) == 0.0


def test_net_balance_to_dr_cr_credit_column_is_absolute() -> None:
    deb, cre = gla.net_balance_to_dr_cr(-77000.0)
    assert deb == 0.0
    assert cre == 77000.0
