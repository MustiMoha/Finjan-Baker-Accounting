"""AR/AP aging bucket alignment for charts."""

from __future__ import annotations

import pandas as pd

import financial_kpis as fkpi


def test_ar_ap_age_buckets_filled_zeros_when_empty() -> None:
    out = fkpi.ar_ap_age_buckets_filled(pd.DataFrame())
    assert list(out["bucket"]) == list(fkpi.AR_AP_AGE_BUCKET_ORDER)
    assert out["amount"].sum() == 0.0


def test_ar_ap_age_buckets_filled_preserves_partial_spikes() -> None:
    sparse = pd.DataFrame({"bucket": ["90+"], "amount": [120_000.0]})
    out = fkpi.ar_ap_age_buckets_filled(sparse)
    assert len(out) == 4
    assert float(out.loc[out["bucket"] == "90+", "amount"].iloc[0]) == 120_000.0
    assert float(out.loc[out["bucket"] == "0–30", "amount"].iloc[0]) == 0.0


def test_ar_ap_age_buckets_filled_deduplicates_bucket_rows() -> None:
    sparse = pd.DataFrame({"bucket": ["90+", "90+"], "amount": [50_000.0, 70_000.0]})
    out = fkpi.ar_ap_age_buckets_filled(sparse)
    assert float(out.loc[out["bucket"] == "90+", "amount"].iloc[0]) == 120_000.0
