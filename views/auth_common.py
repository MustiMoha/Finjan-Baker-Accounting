"""Shared auth page layout and session helpers."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Callable

import streamlit as st

import database as db
from branding import APP_SHORT

_AUTH_CSS_PATH = Path(__file__).resolve().parent.parent / "components" / "auth.css"


def enable_auth_layout() -> None:
    """Apply auth styles to the parent document and the main Streamlit content tree."""
    css = _AUTH_CSS_PATH.read_text(encoding="utf-8")
    inline_css = css.replace("html.baker-auth ", "")
    st.markdown(f"<style id='baker-auth-inline'>{inline_css}</style>", unsafe_allow_html=True)

    css_json = json.dumps(css)
    st.iframe(
        f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head><body>
<script>
(function () {{
  const doc = window.parent.document;
  doc.documentElement.classList.add("baker-auth");
  let el = doc.getElementById("baker-auth-styles");
  if (!el) {{
    el = doc.createElement("style");
    el.id = "baker-auth-styles";
    doc.head.appendChild(el);
  }}
  el.textContent = {css_json};
}})();
</script>
</body></html>
""",
        height=0,
    )


def disable_auth_layout() -> None:
    st.markdown("<style id='baker-auth-inline'></style>", unsafe_allow_html=True)
    st.iframe(
        """
<script>
(function () {
  const doc = window.parent.document;
  doc.documentElement.classList.remove("baker-auth");
  const el = doc.getElementById("baker-auth-styles");
  if (el) el.remove();
})();
</script>
""",
        height=0,
    )


def auth_page_header(*, tagline: str, greeting: str) -> None:
    st.markdown(
        f"""
<p class="auth-brand">{APP_SHORT}</p>
<p class="auth-tagline">{tagline}</p>
<p class="auth-greeting">{greeting}</p>
""",
        unsafe_allow_html=True,
    )


def auth_footer_link(*, prefix: str, link_text: str, href: str) -> None:
    st.markdown(
        f'<p class="auth-footer">{prefix} <a href="{href}" target="_self">{link_text}</a></p>',
        unsafe_allow_html=True,
    )


def _inject_auth_field_width_css() -> None:
    st.markdown(
        """
<style>
div[data-testid="stVerticalBlockBorderWrapper"]:has(.auth-card-panel-marker) {
  width: 360px !important;
  max-width: calc(100vw - 2rem) !important;
  margin-left: auto !important;
  margin-right: auto !important;
  background: #fff !important;
  border: 1px solid #e8edf2 !important;
  border-radius: 18px !important;
  box-shadow: 0 14px 44px rgba(26, 54, 93, 0.11) !important;
  padding: 2.35rem 0 2rem !important;
}
.auth-fields-col [data-testid="stVerticalBlock"],
.auth-fields-col [data-testid="stForm"],
.auth-fields-col [data-testid="stTextInput"],
.auth-fields-col [data-testid="stTextInput"] > div,
.auth-fields-col [data-testid="stTextInput"] input,
.auth-fields-col [data-testid="stFormSubmitButton"],
.auth-fields-col [data-testid="stFormSubmitButton"] button {
  width: 100% !important;
  max-width: 268px !important;
  box-sizing: border-box !important;
}
.auth-fields-col [data-testid="stTextInput"] {
  margin: 0 auto 0.75rem !important;
}
.auth-fields-col [data-testid="stTextInput"] input,
.auth-fields-col [data-testid="stFormSubmitButton"] button {
  border-radius: 8px !important;
}
.auth-fields-col [data-testid="stFormSubmitButton"] button {
  background: #1a365d !important;
  color: #fff !important;
  border: none !important;
  display: block !important;
  margin: 0.5rem auto 0 !important;
}
.auth-fields-col .auth-footer {
  max-width: 268px;
  margin-left: auto;
  margin-right: auto;
}
</style>
""",
        unsafe_allow_html=True,
    )


def auth_card_shell(render_body: Callable[[], None]) -> None:
    enable_auth_layout()
    _inject_auth_field_width_css()
    with st.container(border=True):
        st.markdown('<span class="auth-card-panel-marker" aria-hidden="true"></span>', unsafe_allow_html=True)
        _pad_l, _content, _pad_r = st.columns([0.14, 1, 0.14], gap="small")
        with _content:
            st.markdown('<div class="auth-fields-col">', unsafe_allow_html=True)
            render_body()
            st.markdown("</div>", unsafe_allow_html=True)


def _cookie_manager():
    if "sb_cookie_manager" not in st.session_state:
        try:
            from extra_streamlit_components import CookieManager

            st.session_state.sb_cookie_manager = CookieManager(key="baker_esc_auth_ck")
        except ImportError:
            st.session_state.sb_cookie_manager = None
    return st.session_state.sb_cookie_manager


def persist_auth_cookies(access_token: str, refresh_token: str) -> None:
    cm = _cookie_manager()
    if cm is None:
        return
    exp = datetime.datetime.now() + datetime.timedelta(days=14)
    try:
        cm.batch_set(
            {"baker_sb_access_v1": access_token, "baker_sb_refresh_v1": refresh_token},
            expires_at=exp,
            same_site="lax",
        )
    except Exception:
        pass


def apply_session_from_auth(client, got: dict, *, db_role_to_ui_label) -> None:
    st.session_state.access_token = got["access_token"]
    st.session_state.refresh_token = got["refresh_token"]
    st.session_state.user_email = getattr(got["user"], "email", None) or st.session_state.get("user_email") or ""
    db.set_session(client, got["access_token"], got["refresh_token"])
    try:
        st.session_state.role = db.fetch_user_role(client)
    except Exception:
        st.session_state.role = None
    st.session_state.nav_role_ui = db_role_to_ui_label(st.session_state.role)
    persist_auth_cookies(got["access_token"], got["refresh_token"])
    st.session_state.pop("audit_login_done", None)
    st.session_state.pop("org_gate", None)
    st.rerun()


def auth_switch_link(*, prefix: str, target_path: str) -> None:
    st.markdown(
        f'<p class="auth-footer">{prefix} <a href="/{target_path}" target="_self">Click here</a></p>',
        unsafe_allow_html=True,
    )
