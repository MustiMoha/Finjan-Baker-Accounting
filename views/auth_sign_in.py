"""Sign-in page."""

from __future__ import annotations

import streamlit as st

import database as db
from views import auth_common as ac


def render(client, *, db_role_to_ui_label, sign_up_page=None) -> None:
    def _body() -> None:
        ac.auth_page_header(tagline="Sign in to your workspace", greeting="Welcome back")
        with st.form("sign_in_form", clear_on_submit=False):
            email = st.text_input("Email", key="auth_signin_email", width=268)
            password = st.text_input("Password", type="password", key="auth_signin_pw", width=268)
            submitted = st.form_submit_button("Sign in", type="primary")
            if submitted:
                if not email.strip() or not password:
                    st.warning("Enter your email and password.")
                else:
                    try:
                        got = db.sign_in_email(client, email.strip(), password)
                        ac.apply_session_from_auth(client, got, db_role_to_ui_label=db_role_to_ui_label)
                    except Exception as e:
                        st.error(str(e))
        ac.auth_footer_link(prefix="New here?", link_text="Register", href="/sign-up")

    ac.auth_card_shell(_body)
