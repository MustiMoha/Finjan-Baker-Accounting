"""Viewport-fixed toast stack (parent document) for long Streamlit pages."""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

_TOAST_CSS = """
#baker-toast-host {
  position: fixed;
  bottom: 1.25rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000000;
  display: flex;
  flex-direction: column-reverse;
  align-items: center;
  gap: 0.5rem;
  width: min(92vw, 28rem);
  pointer-events: none;
}
.baker-toast {
  width: 100%;
  padding: 0.65rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.92rem;
  font-weight: 500;
  text-align: center;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.18);
  font-family: "DM Sans", "Segoe UI", system-ui, sans-serif;
  animation: baker-toast-fade 4.5s ease forwards;
}
.baker-toast-success {
  background: #ecfdf3;
  color: #027a48;
  border: 1px solid #abefc6;
}
.baker-toast-error {
  background: #fef3f2;
  color: #b42318;
  border: 1px solid #fecdca;
}
.baker-toast-warning {
  background: #fffaeb;
  color: #b54708;
  border: 1px solid #fedf89;
}
.baker-toast-info {
  background: #eff8ff;
  color: #175cd3;
  border: 1px solid #b2ddff;
}
@keyframes baker-toast-fade {
  0%, 70% { opacity: 1; transform: translateY(0); }
  100% { opacity: 0; transform: translateY(6px); }
}
"""

_KIND_CLASS = {
    "error": "baker-toast-error",
    "warning": "baker-toast-warning",
    "info": "baker-toast-info",
}


def _normalize_items(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in items[-4:]:
        if not isinstance(item, dict):
            continue
        msg = str(item.get("message") or "").strip()
        if not msg:
            continue
        kind = str(item.get("kind") or "success")
        out.append({"kind": kind, "message": msg, "class": _KIND_CLASS.get(kind, "baker-toast-success")})
    return out


def render_viewport_toast_stack(items: list[dict[str, Any]]) -> None:
    """Show toasts fixed to the browser viewport (via parent ``document.body``)."""
    normalized = _normalize_items(items)
    if not normalized:
        return

    payload = json.dumps(normalized)
    css_json = json.dumps(_TOAST_CSS)
    st.iframe(
        f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8"></head><body>
<script>
(function () {{
  const doc = window.parent.document;
  let style = doc.getElementById("baker-toast-styles");
  if (!style) {{
    style = doc.createElement("style");
    style.id = "baker-toast-styles";
    doc.head.appendChild(style);
  }}
  style.textContent = {css_json};

  let host = doc.getElementById("baker-toast-host");
  if (!host) {{
    host = doc.createElement("div");
    host.id = "baker-toast-host";
    doc.body.appendChild(host);
  }}

  const items = {payload};
  for (const item of items) {{
    const el = doc.createElement("div");
    el.className = "baker-toast " + (item.class || "baker-toast-success");
    el.textContent = item.message || "";
    host.appendChild(el);
    window.setTimeout(function () {{
      el.remove();
      if (host && host.childElementCount === 0) {{
        host.remove();
      }}
    }}, 4500);
  }}
}})();
</script>
</body></html>
""",
        height=1,
    )
