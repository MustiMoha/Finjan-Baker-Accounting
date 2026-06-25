"""Trial balance Unknown classification breakdown."""

from __future__ import annotations

import pandas as pd

import gl_analytics as gla


def test_trial_balance_unknown_breakdown_excludes_mapped_liability() -> None:
    df = pd.DataFrame(
        [
            {"account": "Cash", "debit": 100.0, "credit": 0.0},
            {"account": "Mystery counterparty X", "debit": 0.0, "credit": 100.0},
        ]
    )
    maps = [{"kind": "liability", "text": "Mystery counterparty X", "match": "contains"}]
    unk = gla.trial_balance_unknown_breakdown(df, bucket_mappings=maps)
    assert unk.empty


def test_trial_balance_unknown_breakdown_keeps_unmapped() -> None:
    df = pd.DataFrame(
        [
            {"account": "Zyzzyva clearing", "debit": 50.0, "credit": 0.0},
            {"account": "Zyzzyva clearing", "debit": 0.0, "credit": 50.0},
        ]
    )
    unk = gla.trial_balance_unknown_breakdown(df, bucket_mappings=[])
    assert len(unk) == 1
    assert float(unk.iloc[0]["debits"]) == 50.0
    assert float(unk.iloc[0]["credits"]) == 50.0
    assert abs(float(unk.iloc[0]["net_balance"])) < 1e-9
