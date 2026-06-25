"""Organization members: pending join approvals and role / can_approve management."""

from __future__ import annotations

import streamlit as st

import database as db
import org


def _audit_meta() -> tuple[str | None, str | None]:
    ua = ip = None
    ctx = getattr(st, "context", None)
    if ctx is None:
        return ua, ip
    headers = getattr(ctx, "headers", None) or getattr(ctx, "request_headers", None)
    if not headers:
        return ua, ip
    try:
        raw = dict(headers) if hasattr(headers, "keys") else headers
        ua = raw.get("User-Agent") or raw.get("user-agent")
        if ua:
            ua = str(ua)[:2000]
        fwd = raw.get("X-Forwarded-For") or raw.get("x-forwarded-for")
        if fwd:
            ip = str(fwd).split(",")[0].strip()[:128]
    except Exception:
        pass
    return ua, ip


def render_approvals(client) -> None:
    st.session_state["_app_page_marker"] = "member_approvals"
    org_id = org.get_current_org_id()
    ua, ip = _audit_meta()

    st.header("Member approvals")

    if not org.can_approve_members(client, org_id):
        st.warning("You do not have permission to approve new members.")
        return

    pending = org.list_pending_members(client, org_id)
    if not pending:
        st.info("No pending join requests.")
        return

    st.warning(f"{len(pending)} member(s) waiting for approval.")
    for row in pending:
        prof = row.get("profiles") or {}
        email = prof.get("email") or row.get("user_id") or "Unknown"
        mid = str(row["id"])
        with st.container(border=True):
            st.markdown(f"**{email}** — {row.get('job_title') or '—'}")
            st.caption(f"Requested: {row.get('requested_at') or '—'}")
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                role_pick = st.selectbox(
                    "Role on approval",
                    options=["user", "accountant", "admin"],
                    key=f"pending_role_{mid}",
                )
            with c2:
                if st.button("Approve", type="primary", key=f"approve_{mid}"):
                    try:
                        org.approve_member(
                            client,
                            member_id=mid,
                            org_id=org_id,
                            org_role=role_pick,
                            client_ip=ip,
                            user_agent=ua,
                        )
                        st.success("Member approved.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            with c3:
                if st.button("Reject", key=f"reject_{mid}"):
                    try:
                        org.reject_member(
                            client,
                            member_id=mid,
                            org_id=org_id,
                            client_ip=ip,
                            user_agent=ua,
                        )
                        st.info("Request rejected.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))


def render_members(client) -> None:
    st.session_state["_app_page_marker"] = "org_members"
    org_id = org.get_current_org_id()
    ua, ip = _audit_meta()

    st.header("Members")

    if not org.is_org_admin(client, org_id):
        st.warning("Only organization admins can manage members.")
        return

    try:
        members = org.list_org_members(client, org_id)
    except Exception as e:
        st.error(str(e))
        return

    uid_self = ""
    try:
        uid_self = db.get_current_user_id(client)
    except Exception:
        pass

    active = [m for m in members if str(m.get("status")) == "active"]
    if not active:
        st.warning("No active members.")
        return

    for m in active:
        prof = m.get("profiles") or {}
        email = prof.get("email") or m.get("user_id")
        mid = str(m["id"])
        cur_role = str(m.get("org_role") or "user")
        is_owner = cur_role == "owner"
        with st.expander(f"{email} — {cur_role}", expanded=False):
            if is_owner:
                st.caption("Owner — use Organization settings to transfer ownership.")
                continue
            role_opts = ["admin", "accountant", "user"]
            idx = role_opts.index(cur_role) if cur_role in role_opts else 2
            new_role = st.selectbox("Role", options=role_opts, index=idx, key=f"mem_role_{mid}")
            can_ap = st.checkbox(
                "Can approve new members",
                value=bool(m.get("can_approve")),
                key=f"mem_can_ap_{mid}",
                help="Delegates join-request approval without making this user an admin.",
            )
            if st.button("Save changes", key=f"mem_save_{mid}"):
                try:
                    if new_role != cur_role:
                        org.set_member_org_role(
                            client,
                            member_id=mid,
                            org_id=org_id,
                            org_role=new_role,
                            client_ip=ip,
                            user_agent=ua,
                        )
                        if str(m.get("user_id")) == uid_self:
                            org.sync_legacy_user_role(client, new_role)
                    if can_ap != bool(m.get("can_approve")):
                        org.set_member_can_approve(
                            client,
                            member_id=mid,
                            org_id=org_id,
                            can_approve=can_ap,
                            client_ip=ip,
                            user_agent=ua,
                        )
                    st.success("Updated.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


def render(client) -> None:
    render_approvals(client)
    render_members(client)
