"""Organization settings: join code visibility and ownership transfer."""

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


def _set_feedback(slot: str, kind: str, message: str) -> None:
    st.session_state[f"_org_settings_feedback_{slot}"] = {"kind": kind, "message": message}


def _show_feedback(slot: str) -> None:
    payload = st.session_state.pop(f"_org_settings_feedback_{slot}", None)
    if not isinstance(payload, dict):
        return
    message = str(payload.get("message") or "")
    if not message:
        return
    kind = str(payload.get("kind") or "success")
    if kind == "error":
        st.error(message)
    else:
        st.success(message)


def render(client) -> None:
    st.session_state["_app_page_marker"] = "org_settings"
    org_id = org.get_current_org_id()
    ua, ip = _audit_meta()

    st.header("Organization settings")

    org_row = org.fetch_organization(client, org_id)
    if not org_row:
        st.error("Organization not found.")
        return

    st.subheader(org_row.get("name") or "Organization")

    if org.can_view_join_code(client, org_id):
        st.markdown("**Join code** (share with new members)")
        st.code(str(org_row.get("join_code") or ""), language="text")
        st.caption("Visible to the owner and anyone with **Can approve members** enabled.")
    else:
        st.info("Ask your owner or an approver for the join code.")

    mem = org.fetch_active_membership(client, org_id)
    is_owner = bool(mem and str(mem.get("org_role")) == "owner")

    st.divider()
    st.subheader("Transfer ownership")
    if is_owner:
        st.caption(
            "You must transfer ownership before deleting your account or leaving the organization. "
            "The new owner receives full control; you become an admin."
        )
        try:
            members = org.list_org_members(client, org_id)
        except Exception as e:
            st.error(str(e))
            return
        uid = db.get_current_user_id(client)
        candidates = [
            m
            for m in members
            if str(m.get("status")) == "active"
            and str(m.get("user_id")) != uid
            and str(m.get("org_role")) != "owner"
        ]
        if not candidates:
            st.warning("Add another active member before you can transfer ownership.")
        else:
            def _label(m: dict) -> str:
                prof = m.get("profiles") or {}
                em = prof.get("email") or m.get("user_id")
                return f"{em} ({m.get('org_role')})"

            pick = st.selectbox(
                "New owner",
                options=candidates,
                format_func=_label,
                key="xfer_owner_pick",
            )
            confirm = st.checkbox("I understand this cannot be undone from this screen.", key="xfer_confirm")
            if st.button("Transfer ownership", type="primary", disabled=not confirm, key="xfer_btn"):
                try:
                    org.transfer_ownership(
                        client,
                        org_id=org_id,
                        new_owner_user_id=str(pick["user_id"]),
                        client_ip=ip,
                        user_agent=ua,
                    )
                    _set_feedback("xfer", "success", "Ownership transferred.")
                    st.rerun()
                except Exception as e:
                    _set_feedback("xfer", "error", str(e))
            _show_feedback("xfer")
    else:
        st.caption("Only the current owner can transfer ownership.")
