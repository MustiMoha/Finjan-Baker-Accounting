"""Financials view only — all other pages live in the React app at AUTH_WEB_URL."""

from __future__ import annotations

import datetime
import json
import urllib.parse
import urllib.request
from typing import Optional

import streamlit as st

import database as db
import gl_workbook_loader as gl_wb
import org
from branding import APP_NAME, APP_SHORT
from runtime_settings import get_setting
from components import inject_custom_css
from ui_locale import append_locale_to_url, init_locale_from_query, inject_rtl_styles, render_language_toggle, tr
from views import financials


def _client():
    url = get_setting("SUPABASE_URL")
    key = get_setting("SUPABASE_ANON_KEY")
    if not url or not key:
        st.error(
            "Configure SUPABASE_URL and SUPABASE_ANON_KEY "
            "(Fly.io env vars or `.streamlit/secrets.toml`)."
        )
        st.stop()
    if "sb" not in st.session_state:
        st.session_state.sb = db.get_supabase_client(url, key)
    return st.session_state.sb


def _auth_web_url(path: str = "") -> str:
    base = get_setting("AUTH_WEB_URL", "http://127.0.0.1:8000")
    base_s = str(base).rstrip("/")
    if path and not path.startswith("/"):
        path = "/" + path
    return f"{base_s}{path}"


def _redirect_to_auth_web(path: str = "/sign-in") -> None:
    url = _auth_web_url(path)
    st.markdown(f'<meta http-equiv="refresh" content="0;url={url}">', unsafe_allow_html=True)
    st.link_button(tr(f"Continue to {APP_SHORT}"), url)
    st.stop()


def _show_baker_sign_in_required(*, reason: str | None = None) -> None:
    """Stay on Streamlit — avoid auto-redirect loops back through the React app."""
    inject_custom_css()
    inject_rtl_styles()
    st.title(tr("Financials"))
    if reason:
        st.warning(tr(reason))
    try:
        from_handoff = bool(st.query_params.get("handoff_code") or st.query_params.get("access_token"))
    except Exception:
        from_handoff = False
    if from_handoff:
        st.error(
            tr(
                f"{APP_SHORT} sent a sign-in handoff, but Streamlit could not use it "
                "(expired code or API unreachable). Go back to the dashboard, wait a moment, "
                "and click Financials again."
            )
        )
    else:
        st.markdown(
            tr(f"Open **Financials** from the {APP_SHORT} sidebar (while signed in), or use the button below.")
        )
        st.link_button(tr(f"Open Financials via {APP_SHORT}"), _auth_web_url("/financials/open"), type="primary")
    st.link_button(tr(f"Open {APP_SHORT} dashboard"), _auth_web_url("/dashboard"))
    st.stop()


def _show_baker_membership_block(gate: str) -> None:
    inject_custom_css()
    inject_rtl_styles()
    st.title(tr("Financials"))
    labels = {
        "none": tr("You have not joined an organization yet."),
        "pending": tr("Your organization membership is pending approval."),
        "rejected": tr("Your organization membership request was rejected."),
    }
    st.warning(labels.get(gate, tr(f"Your {APP_SHORT} account is not ready for Financials yet.")))
    paths = {"none": "/onboarding", "pending": "/pending", "rejected": "/rejected"}
    st.link_button(tr(f"Continue in {APP_SHORT}"), _auth_web_url(paths.get(gate, "/dashboard")), type="primary")
    st.stop()


_COOKIES_READY_KEY = "_sb_cookies_ready"


def _establish_session(client, access_s: str, refresh_s: str) -> bool:
    """Bind Supabase tokens to the client and persist Streamlit session state."""
    try:
        access_s, refresh_s = db.bind_session_tokens(
            client, access_s, refresh_s, allow_refresh=False
        )
        user = client.auth.get_user(access_s)
        if user.user is None:
            return False
        st.session_state.access_token = access_s
        st.session_state.refresh_token = refresh_s
        st.session_state.user_email = getattr(user.user, "email", None) or ""
        st.session_state.pop("org_gate", None)
        st.session_state.pop("org_id", None)
        st.session_state.pop("audit_login_done", None)
        try:
            st.session_state.role = db.fetch_user_role(client)
        except Exception:
            st.session_state.role = None
        _persist_sb_auth_cookies(access_s, refresh_s)
        return True
    except Exception:
        return False


def _try_restore_from_handoff_code(client) -> bool:
    """Exchange a one-time Baker API handoff code for session tokens."""
    try:
        code = st.query_params.get("handoff_code")
    except Exception:
        return False
    if not code:
        return False
    code_s = str(code[0] if isinstance(code, (list, tuple)) else code)
    url = f"{_auth_web_url('/api/streamlit/exchange')}?code={urllib.parse.quote(code_s)}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        access_s = str(data.get("access_token") or "")
        refresh_s = str(data.get("refresh_token") or "")
    except Exception:
        return False
    if not access_s or not refresh_s:
        return False
    if not _establish_session(client, access_s, refresh_s):
        return False
    try:
        del st.query_params["handoff_code"]
    except Exception:
        pass
    return True


def _try_restore_from_query_params(client) -> bool:
    """Legacy handoff: tokens in the URL (?access_token=&refresh_token=)."""
    qp = st.query_params
    try:
        access = qp.get("access_token")
        refresh = qp.get("refresh_token")
    except Exception:
        return False
    if not access or not refresh:
        return False
    access_s = str(access[0] if isinstance(access, (list, tuple)) else access)
    refresh_s = str(refresh[0] if isinstance(refresh, (list, tuple)) else refresh)
    if not _establish_session(client, access_s, refresh_s):
        return False
    try:
        del st.query_params["access_token"]
        del st.query_params["refresh_token"]
    except Exception:
        pass
    return True


def _sb_cookie_manager_singleton():
    if "sb_cookie_manager" not in st.session_state:
        try:
            from extra_streamlit_components import CookieManager

            st.session_state.sb_cookie_manager = CookieManager(key="baker_esc_auth_ck")
        except ImportError:
            st.session_state.sb_cookie_manager = None
    return st.session_state.sb_cookie_manager


def _persist_sb_auth_cookies(access_token: str, refresh_token: str) -> None:
    cm = _sb_cookie_manager_singleton()
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


def _clear_sb_auth_cookies() -> None:
    cm = _sb_cookie_manager_singleton()
    if cm is None:
        return
    try:
        cm.delete("baker_sb_access_v1", key="sb_ck_del_at")
        cm.delete("baker_sb_refresh_v1", key="sb_ck_del_rt")
    except Exception:
        pass


def _clear_auth_session(*, cookies: bool = True) -> None:
    if cookies:
        _clear_sb_auth_cookies()
    for k in (
        "access_token",
        "refresh_token",
        "role",
        "user_email",
        "audit_login_done",
        "org_gate",
        "org_id",
        _COOKIES_READY_KEY,
    ):
        st.session_state.pop(k, None)


def _try_restore_sb_auth_from_cookies(client) -> bool:
    if st.session_state.get("access_token"):
        return True
    cm = _sb_cookie_manager_singleton()
    if cm is None:
        return False
    try:
        access = cm.get("baker_sb_access_v1")
        refresh = cm.get("baker_sb_refresh_v1")
    except Exception:
        return False
    if not access or not refresh:
        return False
    access_s = str(access)
    refresh_s = str(refresh)
    if not _establish_session(client, access_s, refresh_s):
        _clear_auth_session()
        return False
    return True


def _ensure_auth_from_cookies(client) -> None:
    """
    CookieManager needs one Streamlit rerun before browser cookies are readable.
    """
    if st.session_state.get("access_token"):
        return
    if _try_restore_sb_auth_from_cookies(client):
        return
    if not st.session_state.get(_COOKIES_READY_KEY):
        st.session_state[_COOKIES_READY_KEY] = True
        st.rerun()


def _sync_session(client) -> None:
    """Re-apply the access token only — never refresh (would invalidate the Baker JS session)."""
    tok = st.session_state.get("access_token")
    if not tok:
        return
    tok_s = str(tok)
    if db.access_token_usable(tok_s, skew_sec=90):
        db.apply_access_token(client, tok_s)
        return
    _clear_auth_session(cookies=False)


def _resolve_streamlit_role(client) -> Optional[str]:
    role = st.session_state.get("role")
    if role:
        return str(role)
    try:
        role = db.fetch_user_role(client)
        if role:
            st.session_state.role = role
            return str(role)
    except Exception:
        pass
    try:
        mem = org.fetch_active_membership(client)
        if mem:
            mapped = org.org_role_to_legacy_role(str(mem.get("org_role") or ""))
            st.session_state.role = mapped
            return mapped
    except Exception:
        pass
    return None


def _can_view_financials(client) -> bool:
    role = _resolve_streamlit_role(client)
    return role in ("staff", "admin", "auditor")


def _request_audit_meta() -> tuple[Optional[str], Optional[str]]:
    user_agent = None
    client_ip = None
    ctx = getattr(st, "context", None)
    if ctx is None:
        return user_agent, client_ip
    headers = getattr(ctx, "headers", None) or getattr(ctx, "request_headers", None)
    if headers is None:
        return user_agent, client_ip
    try:
        raw = dict(headers) if hasattr(headers, "keys") else headers
    except Exception:
        raw = {}
    try:
        user_agent = raw.get("User-Agent") or raw.get("user-agent") or raw.get("USER_AGENT")
        if user_agent:
            user_agent = str(user_agent)[:2000]
        fwd = raw.get("X-Forwarded-For") or raw.get("x-forwarded-for")
        if fwd:
            client_ip = str(fwd).split(",")[0].strip()[:128]
        else:
            rip = raw.get("X-Real-Ip") or raw.get("x-real-ip")
            if rip:
                client_ip = str(rip).strip()[:128]
    except Exception:
        pass
    return user_agent, client_ip


def _maybe_log_sign_in(client) -> None:
    if st.session_state.get("audit_login_done"):
        return
    try:
        em = str(st.session_state.get("user_email") or "")[:512]
        rl = str(st.session_state.get("role") or "")[:32]
        ua, ip = _request_audit_meta()
        db.log_sign_in_event(client, email=em or None, role=rl or None, user_agent=ua, client_ip=ip)
    except Exception:
        pass
    st.session_state["audit_login_done"] = True


def _logout(client) -> None:
    _clear_auth_session()
    try:
        db.sign_out(client)
    except Exception:
        pass
    _redirect_to_auth_web("/sign-in")


def main() -> None:
    st.set_page_config(page_title=f"{APP_SHORT} — Financials", layout="wide", initial_sidebar_state="expanded")
    init_locale_from_query()
    client = _client()
    _try_restore_from_handoff_code(client) or _try_restore_from_query_params(client)
    _ensure_auth_from_cookies(client)

    if not st.session_state.get("access_token"):
        _show_baker_sign_in_required(
            reason=tr(
                "No active session was found for this browser. "
                f"Financials must be opened from {APP_SHORT} at least once while signed in."
            ),
        )

    inject_custom_css()
    inject_rtl_styles()
    _sync_session(client)

    if not st.session_state.get("access_token"):
        _show_baker_sign_in_required(
            reason=tr(f"Your Financials session expired. Click Financials in {APP_SHORT} again."),
        )

    try:
        gate = org.resolve_membership_gate(client)
        st.session_state["org_gate"] = gate
    except Exception:
        gate = "none"
        st.session_state["org_gate"] = gate

    if gate != "active":
        _show_baker_membership_block(gate)

    org_id = org.get_current_org_id(client)
    st.session_state["org_id"] = org_id
    _maybe_log_sign_in(client)

    if not _can_view_financials(client):
        st.error(tr("Your role does not include Financials."))
        st.markdown(
            f'<a href="{_auth_web_url("/dashboard")}" target="_self" style="text-decoration:none;">'
            f'<span style="display:inline-block;padding:0.4rem 1rem;border-radius:0.5rem;'
            f'border:1px solid #0d9488;color:#0f766e;font-weight:600;">{tr(f"Back to {APP_SHORT}")}</span></a>',
            unsafe_allow_html=True,
        )
        return

    with st.sidebar:
        st.markdown(f"### {tr('Financials')}")
        render_language_toggle(key_prefix="sidebar")
        st.caption(st.session_state.get("user_email") or "")
        try:
            org_row = org.fetch_organization(client, org_id)
            if org_row:
                st.caption(f"**{org_row.get('name') or tr('Organization')}**")
        except Exception:
            pass
        baker_url = append_locale_to_url(_auth_web_url("/dashboard"))
        st.markdown(
            f'<a href="{baker_url}" target="_self" style="display:block;width:100%;text-align:center;'
            f'text-decoration:none;padding:0.5rem 1rem;border-radius:0.5rem;border:1px solid #0d9488;'
            f'color:#0f766e;font-weight:600;background:#f0fdfa;">← {tr(f"Back to {APP_SHORT}")}</a>',
            unsafe_allow_html=True,
        )
        st.radio(
            tr("Show amounts in:"),
            ["Original Currency", "USD (Reporting)"],
            format_func=tr,
            key="dashboard_currency_view",
            help=tr(
                "Original: numbers as entered in the spreadsheet. "
                "USD: converted using exchange rates in Settings."
            ),
        )
        if st.button(tr("Sign out"), width="stretch"):
            _logout(client)

    gl_wb.mark_financials_navigation_and_refresh_workbook(client, dict(st.secrets))
    financials.render(client)


if __name__ == "__main__":
    main()
