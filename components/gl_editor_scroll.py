"""Preserve Glide data-grid scroll inside ``st.data_editor`` across fragment reruns."""

from __future__ import annotations

import json
import re

import streamlit as st

_IFRAME_HEIGHT = 1
_GLIDE_ROW_PX = 36
_HOOK_FLAG = "baker_gl_scroll_hook_installed"


def _js_scope_token(scope_id: str) -> str:
    return re.sub(r"\W+", "_", scope_id or "gl")[:48]


def _focus_row_key(scope_id: str) -> str:
    return f"baker_gl_focus_row_{_js_scope_token(scope_id)}"


def set_focus_display_row(scope_id: str, row_index: int | None) -> None:
    if row_index is None or row_index < 0:
        return
    st.session_state[_focus_row_key(scope_id)] = int(row_index)


def get_focus_display_row(scope_id: str) -> int:
    try:
        return max(0, int(st.session_state.get(_focus_row_key(scope_id), 0) or 0))
    except (TypeError, ValueError):
        return 0


def _glide_script(*, token: str, phase: str, focus_row: int) -> str:
    storage_key = json.dumps(f"baker_gl_glide_{token}")
    anchor_id = json.dumps(f"baker-gl-anchor-{token}")
    phase_json = json.dumps(phase)
    row_px = _GLIDE_ROW_PX
    focus_json = int(max(0, focus_row))
    return f"""
(function () {{
  const win = window.parent;
  const doc = win.document;
  const STORAGE_KEY = {storage_key};
  const ANCHOR_ID = {anchor_id};
  const PHASE = {phase_json};
  const ROW_PX = {row_px};
  const FOCUS_ROW = {focus_json};

  function editorForAnchor() {{
    const anchor = doc.getElementById(ANCHOR_ID);
    if (!anchor) return null;
    let node = anchor.parentElement;
    for (let i = 0; i < 24 && node; i++) {{
      const ed = node.querySelector('[data-testid="stDataEditor"]');
      if (ed) return ed;
      node = node.parentElement;
    }}
    return null;
  }}

  function scroller() {{
    const ed = editorForAnchor();
    if (!ed) return null;
    return ed.querySelector(".dvn-scroller");
  }}

  function targetTop(payload) {{
    const fromRow = FOCUS_ROW > 0 ? FOCUS_ROW * ROW_PX : 0;
    const fromStore =
      payload && typeof payload.top === "number" ? payload.top : 0;
    return Math.max(fromRow, fromStore);
  }}

  function readStore() {{
    try {{
      const raw = win.sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return {{ top: 0, left: 0 }};
      return JSON.parse(raw);
    }} catch (e) {{
      return {{ top: 0, left: 0 }};
    }}
  }}

  function writeStore(g) {{
    if (!g) return;
    try {{
      win.sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({{ top: g.scrollTop || 0, left: g.scrollLeft || 0 }})
      );
    }} catch (e) {{}}
  }}

  function applyTop(top, left) {{
    const g = scroller();
    if (!g || top < 0) return false;
    if (Math.abs((g.scrollTop || 0) - top) > 1) {{
      g.scrollTop = top;
    }}
    if (typeof left === "number" && Math.abs((g.scrollLeft || 0) - left) > 1) {{
      g.scrollLeft = left;
    }}
    return true;
  }}

  function restoreNow() {{
    const payload = readStore();
    const top = targetTop(payload);
    return applyTop(top, payload.left || 0);
  }}

  function armGuard(ms) {{
    const payload = readStore();
    const wantTop = targetTop(payload);
    if (wantTop <= 0) return;
    const end = Date.now() + ms;
    const tick = () => {{
      const g = scroller();
      if (g) {{
        if ((g.scrollTop || 0) < wantTop - 8) {{
          g.scrollTop = wantTop;
        }}
        writeStore(g);
      }}
      if (Date.now() < end) win.requestAnimationFrame(tick);
    }};
    tick();
    [0, 16, 50, 100, 200, 400, 800, 1200, 2000, 3000].forEach((t) => {{
      win.setTimeout(restoreNow, t);
    }});
  }}

  if (PHASE === "hook") {{
    if (!win.__bakerGlGlideHook) {{
      win.__bakerGlGlideHook = true;
      doc.addEventListener(
        "scroll",
        (ev) => {{
          const t = ev.target;
          if (!t || !t.classList || !t.classList.contains("dvn-scroller")) return;
          const ed = editorForAnchor();
          if (!ed || !ed.contains(t)) return;
          writeStore(t);
        }},
        true
      );
      const native = Element.prototype.scrollIntoView;
      Element.prototype.scrollIntoView = function (...args) {{
        const ed = editorForAnchor();
        if (ed && ed.contains(this)) {{
          const g = scroller();
          if (g) writeStore(g);
          return;
        }}
        return native.apply(this, args);
      }};
    }}
    const g = scroller();
    if (g) writeStore(g);
    return;
  }}

  restoreNow();
  armGuard(3500);
  const obs = new win.MutationObserver(() => restoreNow());
  obs.observe(doc.body, {{ childList: true, subtree: true }});
  win.setTimeout(() => obs.disconnect(), 4000);
}})();
"""


def _inject(phase: str, scope_id: str, *, focus_row: int = 0) -> None:
    token = _js_scope_token(scope_id)
    st.iframe(
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\"></head><body>"
        f"<script>{_glide_script(token=token, phase=phase, focus_row=focus_row)}</script>"
        "</body></html>",
        height=_IFRAME_HEIGHT,
    )


def mount_gl_editor_scroll_anchor(scope_id: str) -> None:
    """Anchor + one-time Glide scroll capture (before ``st.data_editor``)."""
    token = _js_scope_token(scope_id)
    st.markdown(
        f'<div id="baker-gl-anchor-{token}" aria-hidden="true" style="height:0;margin:0;"></div>',
        unsafe_allow_html=True,
    )
    if not st.session_state.get(_HOOK_FLAG):
        st.session_state[_HOOK_FLAG] = True
        _inject("hook", scope_id)


def restore_gl_editor_scroll(scope_id: str, *, focus_row: int | None = None) -> None:
    """Restore Glide ``.dvn-scroller`` position after the grid renders."""
    row = focus_row if focus_row is not None else get_focus_display_row(scope_id)
    _inject("restore", scope_id, focus_row=row)


def mount_gl_editor_scroll_preserve(scope_id: str) -> None:
    mount_gl_editor_scroll_anchor(scope_id)
