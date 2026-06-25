"""Convert GL row amounts into a reporting currency using admin-configured multipliers."""

from __future__ import annotations

from typing import Any

import pandas as pd


def normalize_fx_rates(raw: Any) -> dict[str, float]:
    if raw is None or not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        iso = str(k).strip().upper()[:3]
        if len(iso) != 3:
            continue
        try:
            f = float(v)
            if f > 0:
                out[iso] = f
        except (TypeError, ValueError):
            continue
    return out


def multiplier_to_display(row_iso: str, display_iso: str, rates: dict[str, float]) -> tuple[float, str | None]:
    """
    amount_in_display = amount_in_row * multiplier
    rates[ROW] = units of display currency per 1 unit of ROW (e.g. USD per EUR).
    """
    row_i = (row_iso or "").strip().upper()[:3]
    disp_i = (display_iso or "").strip().upper()[:3]
    if len(row_i) < 3:
        row_i = "USD"
    if len(disp_i) < 3:
        disp_i = "USD"
    if row_i == disp_i:
        return 1.0, None
    if row_i in rates:
        return rates[row_i], None
    return 1.0, f"Missing FX rate for {row_i} (reporting {disp_i}); using ×1 — set rate in Configuration."


def apply_display_currency(
    df: pd.DataFrame,
    display_iso: str,
    rates: dict[str, float],
    *,
    currency_col: str = "currency_iso",
) -> tuple[pd.DataFrame, list[str]]:
    """Add debit_display, credit_display; duplicate net helpers. Collects conversion warnings."""
    if df.empty:
        return df.copy(), []
    out = df.copy()
    warnings: list[str] = []
    mults: list[float] = []
    for _, r in out.iterrows():
        m, w = multiplier_to_display(str(r.get(currency_col) or ""), display_iso, rates)
        mults.append(m)
        if w:
            warnings.append(w)
    out["_fx_mult"] = mults
    out["debit_display"] = out["debit"].astype(float) * out["_fx_mult"]
    out["credit_display"] = out["credit"].astype(float) * out["_fx_mult"]
    out = out.drop(columns=["_fx_mult"])
    deduped = list(dict.fromkeys(warnings))
    return out, deduped
