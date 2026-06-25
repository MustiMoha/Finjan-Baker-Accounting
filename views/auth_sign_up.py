"""Create account page."""

from __future__ import annotations

import streamlit as st

import database as db
from views import auth_common as ac


def render(client, *, db_role_to_ui_label, sign_in_page=None) -> None:
    def _body() -> None:
        ac.auth_page_header(tagline="Create your workspace account", greeting="Get started")
        with st.form("sign_up_form", clear_on_submit=False):
            email = st.text_input("Email", key="auth_signup_email", width=268)
            password = st.text_input("Password", type="password", key="auth_signup_pw", width=268)
            confirm = st.text_input("Confirm password", type="password", key="auth_signup_confirm", width=268)
            submitted = st.form_submit_button("Register", type="primary")
            if submitted:
                if not email.strip() or not password:
                    st.warning("Enter email and password.")
                elif len(password) < 8:
                    st.warning("Password must be at least 8 characters.")
                elif password != confirm:
                    st.error("Passwords do not match.")
                else:
                    try:
                        got = db.sign_up_email(client, email.strip(), password)
                        if got.get("session_ready"):
                            ac.apply_session_from_auth(client, got, db_role_to_ui_label=db_role_to_ui_label)
                        else:
                            st.success(
                                "Account created. If email confirmation is enabled, check your inbox — "
                                "then sign in."
                            )
                    except Exception as e:
                        st.error(str(e))
        ac.auth_footer_link(prefix="Already have an account?", link_text="Sign in", href="/sign-in")

    ac.auth_card_shell(_body)
