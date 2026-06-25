"""Admin: organization audit trail and sign-in history."""

from __future__ import annotations

import streamlit as st

import database as db
import org


def render(client) -> None:
    st.session_state["_app_page_marker"] = "audit"
    org_id = org.get_current_org_id()

    st.header("Audit log")

    tab_org, tab_signin = st.tabs(["Organization events", "Sign-in history"])

    with tab_org:
        lim = st.number_input("Rows to show", min_value=50, max_value=2000, value=200, step=50, key="audit_org_lim")
        try:
            rows = org.fetch_audit_logs(client, org_id, limit=int(lim))
        except Exception as e:
            st.error(str(e))
            rows = []

        if not rows:
            st.info("No organization events logged yet.")
        else:
            st.dataframe(
                rows,
                width="stretch",
                hide_index=True,
                column_order=["occurred_at", "action", "success", "actor_user_id", "target_user_id", "client_ip", "details"],
                column_config={
                    "occurred_at": st.column_config.DatetimeColumn("When"),
                    "action": st.column_config.TextColumn("Action"),
                    "success": st.column_config.CheckboxColumn("OK"),
                    "actor_user_id": st.column_config.TextColumn("Actor"),
                    "target_user_id": st.column_config.TextColumn("Target user"),
                    "client_ip": st.column_config.TextColumn("IP"),
                    "details": st.column_config.JsonColumn("Details"),
                },
            )

    with tab_signin:
        lim2 = st.number_input(
            "Sign-in rows",
            min_value=50,
            max_value=2000,
            value=500,
            step=50,
            key="audit_signin_lim",
        )
        try:
            rows2 = db.fetch_audit_sign_ins(client, limit=int(lim2))
        except Exception as e:
            st.error(str(e))
            st.info("Run the database migration that adds **audit_sign_ins**.")
            rows2 = []

        if not rows2:
            st.info("Nothing logged yet.")
        else:
            st.dataframe(
                rows2,
                width="stretch",
                hide_index=True,
                column_order=["occurred_at", "email", "role", "user_id", "client_ip", "user_agent"],
                column_config={
                    "occurred_at": st.column_config.DatetimeColumn("When"),
                    "email": st.column_config.TextColumn("Email"),
                    "role": st.column_config.TextColumn("Role at sign-in"),
                    "user_id": st.column_config.TextColumn("User ID"),
                    "client_ip": st.column_config.TextColumn("Network address"),
                    "user_agent": st.column_config.TextColumn("Browser info", width="large"),
                },
            )
