"""GL edit helpers: inline HTML (no declare_component) for row-hover insert actions."""

from __future__ import annotations

import html
from typing import Any

import pandas as pd
import streamlit as st

_MAX_EDIT_ROWS = 250
_MAX_HOVER_ROWS = _MAX_EDIT_ROWS


def component_payload_to_dataframe(
    rows: list[dict[str, Any]],
    *,
    include_tr: bool,
) -> pd.DataFrame:
    cols = ["_excel_row", "After row", "Date", "Account", "Debit", "Credit", "Details"]
    if include_tr:
        cols.append("Tr")
    if not rows:
        return pd.DataFrame(columns=cols)
    built: list[dict[str, Any]] = []
    for r in rows:
        built.append(
            {
                "_excel_row": int(r.get("excel_row") or 0),
                "After row": int(r.get("after_row") or 0),
                "Date": str(r.get("date") or ""),
                "Account": str(r.get("account") or ""),
                "Debit": float(r.get("debit") or 0),
                "Credit": float(r.get("credit") or 0),
                "Details": str(r.get("details") or ""),
                **({"Tr": str(r.get("tr") or "")} if include_tr else {}),
            }
        )
    return pd.DataFrame(built)


def _esc(text: object) -> str:
    return html.escape(str(text or ""), quote=True)


def _fmt_amt(v: object) -> str:
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


def hover_insert_table_html(df: pd.DataFrame, *, include_tr: bool) -> str:
    """Read-only row strip; +↑ / +↓ set ``gl_ins`` on the parent page URL."""
    if df.empty:
        return "<p style='color:#64748b;padding:12px;'>No rows.</p>"

    tr_th = "<th>Tr</th>" if include_tr else ""
    body: list[str] = []
    for rec in df.to_dict(orient="records"):
        er = int(rec.get("_excel_row") or 0)
        if er < 1:
            continue
        tr_td = (
            f"<td class='c'>{_esc(rec.get('Tr', ''))}</td>"
            if include_tr
            else ""
        )
        acct = _esc(rec.get("Account") or "")
        if len(acct) > 36:
            acct = acct[:33] + "…"
        body.append(
            f"""<tr class="gl-row">
  <td class="act">
    <button type="button" class="geb" onclick="glIns('above',{er})" title="Insert above">+↑</button>
    <button type="button" class="geb" onclick="glIns('below',{er})" title="Insert below">+↓</button>
  </td>
  <td class="c mono">{er}</td>
  {tr_td}
  <td class="c">{_esc(rec.get('Date', ''))}</td>
  <td class="c">{acct}</td>
  <td class="c num">{_fmt_amt(rec.get('Debit'))}</td>
  <td class="c num">{_fmt_amt(rec.get('Credit'))}</td>
  <td class="c">{_esc(rec.get('Details', ''))}</td>
</tr>"""
        )

    if not body:
        return "<p style='color:#64748b;padding:12px;'>No sheet rows in this slice.</p>"

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 0; font: 13px/1.35 "Segoe UI", system-ui, sans-serif; color: #0f172a; }}
table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
thead th {{
  text-align: left; font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.04em; color: #64748b; padding: 6px 4px; border-bottom: 2px solid #e2e8f0; background: #f8fafc;
}}
thead th.act-h {{ width: 76px; text-align: center; }}
tbody tr.gl-row {{ height: 34px; }}
tbody tr.gl-row:hover {{ background: rgba(20, 184, 166, 0.08); }}
td {{ padding: 4px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
td.act {{ text-align: center; opacity: 0; transition: opacity 0.12s; width: 76px; }}
tr.gl-row:hover td.act {{ opacity: 1; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
td.mono {{ color: #64748b; font-size: 11px; }}
.geb {{
  border: 1px solid rgba(20, 184, 166, 0.5); background: #fff; color: #0d9488;
  border-radius: 4px; font-size: 11px; font-weight: 700; padding: 2px 6px; margin: 0 1px; cursor: pointer;
}}
.geb:hover {{ background: rgba(20, 184, 166, 0.14); }}
</style>
</head>
<body>
<table>
<thead><tr>
  <th class="act-h"></th>
  <th style="width:44px">Row</th>
  {tr_th}
  <th style="width:88px">Date</th>
  <th>Account</th>
  <th style="width:72px">Debit</th>
  <th style="width:72px">Credit</th>
  <th>Details</th>
</tr></thead>
<tbody>
{"".join(body)}
</tbody>
</table>
<script>
function glIns(kind, row) {{
  try {{
    const top = window.top || window.parent;
    const u = new URL(top.location.href);
    u.searchParams.set("gl_ins", kind + ":" + String(row));
    top.location.href = u.toString();
  }} catch (e) {{
    console.error("glIns failed", e);
  }}
}}
</script>
</body></html>"""


def render_hover_insert_table(df: pd.DataFrame, *, include_tr: bool) -> None:
    """Hover +↑ / +↓ on each ledger row (inline HTML, works on Streamlit Cloud)."""
    n = max(1, min(len(df), _MAX_HOVER_ROWS))
    h = min(720, 52 + n * 34)
    doc = hover_insert_table_html(df.head(_MAX_HOVER_ROWS), include_tr=include_tr)
    st.iframe(doc, height=h)
