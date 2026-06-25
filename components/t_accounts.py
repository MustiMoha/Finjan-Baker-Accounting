"""Classic T-account diagrams (HTML) for Streamlit via st.iframe."""

from __future__ import annotations

import html
import math
from typing import Any

import streamlit as st

_TEAL = "#14b8a6"
_TEAL_DIM = "rgba(20, 184, 166, 0.14)"
_SLATE = "#64748b"
_TEXT = "#0f172a"
_MUTED = "#64748b"
_BORDER = "rgba(148, 163, 184, 0.35)"


def _esc(text: object) -> str:
    return html.escape(str(text or ""), quote=True)


def _fmt_amount(value: float, *, prefix: str = "") -> str:
    if not math.isfinite(value):
        value = 0.0
    sign = "-" if value < 0 else ""
    body = f"{abs(value):,.2f}"
    p = prefix.strip()
    return f"{sign}{p}{body}" if p else f"{sign}{body}"


def _balance_label(net: float) -> str:
    if abs(net) < 1e-9:
        return "Balanced"
    if net > 0:
        return f"Debit balance · {_fmt_amount(net)}"
    return f"Credit balance · {_fmt_amount(abs(net))}"


_OPENING_DESCRIPTIONS = frozenset(
    {"beginning balance", "opening balance", "opening", "brought forward"}
)


def _is_opening_description(desc: object) -> bool:
    key = str(desc or "").strip().casefold()
    if key in _OPENING_DESCRIPTIONS or key.startswith("opening "):
        return True
    return "brought forward" in key or "carried forward" in key


def _opening_display_label(desc: object, *, fallback: str = "Opening balance") -> str:
    key = str(desc or "").strip().casefold()
    if "brought forward" in key or key == "brought forward":
        return "Brought forward"
    if key.startswith("beginning balance") or key in {"opening balance", "opening"}:
        return "Beginning balance"
    if "beginning balance" in key and "brought forward" in key:
        return "Beginning balance / Brought forward"
    return fallback


def _opening_line_html(label: str, amount: float, *, prefix: str) -> str:
    """First line on a T-account column (opening / beginning balance)."""
    return (
        f'<div class="tac-line tac-open">{_esc(label)}<br>'
        f'<span class="v">{_esc(_fmt_amount(amount, prefix=prefix))}</span></div>'
    )


def _grid_height(n_cards: int, *, cols: int = 3) -> int:
    rows = max(1, (max(0, n_cards) + cols - 1) // cols)
    return min(2400, max(320, 24 + rows * 168))


def _detail_height(n_debits: int, n_credits: int) -> int:
    rows = max(n_debits, n_credits, 1)
    return min(900, max(280, 120 + rows * 26))


def _base_styles() -> str:
    return f"""
.tac-wrap {{
  font-family: "DM Sans", "Segoe UI", system-ui, sans-serif;
  color: {_TEXT};
  margin: 0;
  padding: 2px 0;
}}
.tac-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}}
.tac-card {{
  border: 1px solid {_BORDER};
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 2px 10px rgba(15, 23, 42, 0.05);
  overflow: hidden;
}}
.tac-title {{
  font-size: 0.78rem;
  font-weight: 600;
  text-align: center;
  padding: 8px 10px 6px;
  line-height: 1.25;
  border-bottom: 2px solid {_TEXT};
  word-break: break-word;
}}
.tac-body {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: 72px;
}}
.tac-col {{
  padding: 6px 8px 4px;
  font-size: 0.7rem;
}}
.tac-col.debit {{
  border-right: 1px solid {_BORDER};
  background: {_TEAL_DIM};
}}
.tac-col.credit {{
  background: #f8fafc;
}}
.tac-h {{
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: {_MUTED};
  margin-bottom: 4px;
}}
.tac-amt {{
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  font-size: 0.82rem;
  color: {_TEXT};
}}
.tac-line {{
  font-size: 0.66rem;
  color: {_TEXT};
  margin: 3px 0;
  line-height: 1.2;
  word-break: break-word;
}}
.tac-line .v {{
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: {_TEAL};
}}
.tac-line.tac-open {{
  margin-bottom: 6px;
  padding-bottom: 5px;
  border-bottom: 1px dashed {_BORDER};
}}
.tac-foot {{
  font-size: 0.68rem;
  text-align: center;
  padding: 5px 8px 7px;
  border-top: 1px solid {_BORDER};
  color: {_MUTED};
  background: #f8fafc;
}}
.tac-detail {{
  max-width: 640px;
  margin: 0 auto;
}}
.tac-detail .tac-body {{
  min-height: 96px;
}}
"""


def t_accounts_summary_grid(
    accounts: list[dict[str, Any]],
    *,
    currency_prefix: str = "",
    title: str = "",
) -> None:
    """
    One T-account card per row in ``accounts`` (keys: account, debits, credits, net_balance).
    """
    cards_html: list[str] = []
    pref = currency_prefix.strip()
    for row in accounts:
        acct = _esc(row.get("account") or "")
        deb = float(row.get("debits") or 0)
        cre = float(row.get("credits") or 0)
        opening = float(row.get("opening_balance") or 0)
        net = float(row.get("net_balance") if row.get("net_balance") is not None else deb - cre)
        open_label = str(row.get("opening_label") or "").strip() or "Opening balance"
        deb_open = ""
        cre_open = ""
        if abs(opening) > 1e-9:
            if opening > 1e-9:
                deb_open = _opening_line_html(open_label, opening, prefix=pref)
            else:
                cre_open = _opening_line_html(open_label, abs(opening), prefix=pref)
        cards_html.append(
            f"""
<div class="tac-card">
  <div class="tac-title">{acct}</div>
  <div class="tac-body">
    <div class="tac-col debit">
      <div class="tac-h">Debit</div>
      {deb_open}
      <div class="tac-amt">{_esc(_fmt_amount(deb, prefix=pref))}</div>
    </div>
    <div class="tac-col credit">
      <div class="tac-h">Credit</div>
      {cre_open}
      <div class="tac-amt">{_esc(_fmt_amount(cre, prefix=pref))}</div>
    </div>
  </div>
  <div class="tac-foot">{_esc(_balance_label(net))}</div>
</div>"""
        )

    title_html = f'<div style="font-size:0.9rem;font-weight:600;margin:0 0 10px;">{_esc(title)}</div>' if title else ""
    body = (
        f"{title_html}<div class=\"tac-grid\">{''.join(cards_html)}</div>"
        if cards_html
        else '<p style="color:#64748b;font-size:0.85rem;">No accounts to show.</p>'
    )
    h = _grid_height(len(cards_html))
    doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{_base_styles()}</style></head>
<body class="tac-wrap">{body}</body></html>"""
    st.iframe(doc, height=h)


def t_account_detail(
    account: str,
    entries: list[dict[str, Any]],
    *,
    total_debits: float,
    total_credits: float,
    net_balance: float,
    currency_prefix: str = "",
    title: str = "",
) -> None:
    """
    Line-level T-account: debit legs left, credit legs right.

    Each entry may include ``description``, ``debit``, ``credit`` (floats).
    """
    pref = currency_prefix.strip()
    deb_open: list[str] = []
    cre_open: list[str] = []
    deb_lines: list[str] = []
    cre_lines: list[str] = []
    for ent in entries:
        raw_desc = str(ent.get("description") or "—")
        desc = _esc(raw_desc)
        d = float(ent.get("debit") or 0)
        c = float(ent.get("credit") or 0)
        is_open = _is_opening_description(raw_desc)
        if d > 1e-9:
            line = (
                f'<div class="tac-line{" tac-open" if is_open else ""}">{desc}<br>'
                f'<span class="v">{_esc(_fmt_amount(d, prefix=pref))}</span></div>'
            )
            (deb_open if is_open else deb_lines).append(line)
        if c > 1e-9:
            line = (
                f'<div class="tac-line{" tac-open" if is_open else ""}">{desc}<br>'
                f'<span class="v">{_esc(_fmt_amount(c, prefix=pref))}</span></div>'
            )
            (cre_open if is_open else cre_lines).append(line)
    deb_lines = deb_open + deb_lines
    cre_lines = cre_open + cre_lines

    if not deb_lines:
        deb_lines.append('<div class="tac-line" style="color:#94a3b8;">—</div>')
    if not cre_lines:
        cre_lines.append('<div class="tac-line" style="color:#94a3b8;">—</div>')

    tit = _esc(title or account)
    foot = _esc(_balance_label(net_balance))
    tot_d = _esc(_fmt_amount(total_debits, prefix=pref))
    tot_c = _esc(_fmt_amount(total_credits, prefix=pref))

    doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{_base_styles()}</style></head>
<body class="tac-wrap">
<div class="tac-detail">
  <div class="tac-card">
    <div class="tac-title">{tit}</div>
    <div class="tac-body">
      <div class="tac-col debit">
        <div class="tac-h">Debit</div>
        {''.join(deb_lines)}
        <div class="tac-amt" style="margin-top:8px;border-top:1px solid {_BORDER};padding-top:4px;">Σ {tot_d}</div>
      </div>
      <div class="tac-col credit">
        <div class="tac-h">Credit</div>
        {''.join(cre_lines)}
        <div class="tac-amt" style="margin-top:8px;border-top:1px solid {_BORDER};padding-top:4px;">Σ {tot_c}</div>
      </div>
    </div>
    <div class="tac-foot">{foot}</div>
  </div>
</div>
</body></html>"""
    st.iframe(doc, height=_detail_height(len(deb_lines), len(cre_lines)))
