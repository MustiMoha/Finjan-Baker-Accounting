"""Balance sheet consolidation of trade A/P lines."""

from __future__ import annotations

import pandas as pd

import gl_analytics as gla


def test_trade_ap_match_a_policy_safe() -> None:
    assert not gla._is_trade_payable_balance_sheet_line("a/policy renewal")
    assert gla._is_trade_payable_balance_sheet_line("A/P ( Nouga)")
    assert gla._is_trade_payable_balance_sheet_line("Accounts payable – vendor")


def test_roll_up_merge_split_ap_aliases() -> None:
    df = pd.DataFrame(
        [
            {"account": "A/P (wood work)", "debits": 0.0, "credits": 8870.0, "net_balance": -8870.0},
            {"account": "A/P (Woodwork)", "debits": 5322.0, "credits": 0.0, "net_balance": 5322.0},
            {"account": "Cheques Payable", "debits": 0.0, "credits": 449722.0, "net_balance": -449722.0},
            {"account": "A/P Ali", "debits": 0.0, "credits": 0.0, "net_balance": 0.0},
        ]
    )
    out = gla.rollup_trade_payables_for_balance_sheet(df)
    ap = out.loc[out["account"] == "Accounts payable (A/P)"].iloc[0]
    assert float(ap["debits"]) == 5322.0
    assert float(ap["credits"]) == 8870.0
    assert len(out[out["account"].str.startswith("A/P")]) == 0
    assert len(out[out["account"] == "Cheques Payable"]) == 1


def test_roll_up_returns_copy_when_empty() -> None:
    assert gla.rollup_trade_payables_for_balance_sheet(pd.DataFrame()).empty
