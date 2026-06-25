"""Post-registration onboarding: create or join an organization."""

from __future__ import annotations

import streamlit as st

import org


def _audit_meta() -> tuple[str | None, str | None]:
    ua = ip = None
    ctx = getattr(st, "context", None)
    if ctx is None:
        return ua, ip
    headers = getattr(ctx, "headers", None) or getattr(ctx, "request_headers", None)
    if headers is None:
        return ua, ip
    try:
        raw = dict(headers) if hasattr(headers, "keys") else headers
    except Exception:
        return ua, ip
    try:
        ua = raw.get("User-Agent") or raw.get("user-agent")
        if ua:
            ua = str(ua)[:2000]
        fwd = raw.get("X-Forwarded-For") or raw.get("x-forwarded-for")
        if fwd:
            ip = str(fwd).split(",")[0].strip()[:128]
    except Exception:
        pass
    return ua, ip


def render(client) -> None:
    st.header("Welcome")
    st.caption("Create a new organization or join an existing one with a 6-character code.")

    tab_create, tab_join = st.tabs(["Create organization", "Join organization"])
    ua, ip = _audit_meta()

    with tab_create:
        st.subheader("Create organization")
        st.caption("You will become the **Owner** with full control, including the first workbook upload.")
        org_name = st.text_input("Organization name", key="onboard_org_name")
        job_title = st.text_input("Your title (e.g. CFO, Controller)", key="onboard_create_title")
        if st.button("Create organization", type="primary", key="onboard_create_btn"):
            try:
                created = org.create_organization(
                    client,
                    name=org_name,
                    job_title=job_title,
                    client_ip=ip,
                    user_agent=ua,
                )
                st.session_state["org_id"] = str(created["id"])
                st.session_state["org_gate"] = "active"
                st.success(f"Organization **{created['name']}** created. Your join code is **{created['join_code']}**.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    with tab_join:
        st.subheader("Join organization")
        st.caption("Enter the code from your administrator. An approver must activate your account before you can access data.")
        join_code = st.text_input(
            "6-character join code",
            max_chars=6,
            key="onboard_join_code",
            help="Letters A–Z and digits 0–9.",
        ).strip().upper()
        join_title = st.text_input("Your title", key="onboard_join_title")
        if st.button("Request to join", type="primary", key="onboard_join_btn"):
            try:
                org.request_join_organization(
                    client,
                    join_code=join_code,
                    job_title=join_title,
                    client_ip=ip,
                    user_agent=ua,
                )
                st.session_state["org_gate"] = "pending"
                st.success("Request submitted. You will be notified once an approver accepts you.")
                st.rerun()
            except Exception as e:
                st.error(str(e))
