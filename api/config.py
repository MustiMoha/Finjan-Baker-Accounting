"""Load Supabase credentials from environment or Streamlit secrets."""

from __future__ import annotations

from typing import Any

from runtime_settings import cors_allowed_origins, get_setting, serve_auth_ui


def supabase_url() -> str:
    return get_setting("SUPABASE_URL")


def supabase_anon_key() -> str:
    return get_setting("SUPABASE_ANON_KEY")


def supabase_service_role_key() -> str:
    return get_setting("SUPABASE_SERVICE_ROLE_KEY")


def auth_web_url() -> str:
    return get_setting("AUTH_WEB_URL", "http://127.0.0.1:8000")


def streamlit_url() -> str:
    return get_setting("STREAMLIT_URL", "http://127.0.0.1:8501")


def streamlit_secrets_dict() -> dict[str, Any]:
    """Secrets for workbook loading (same keys as .streamlit/secrets.toml)."""
    keys = (
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "MASTER_WORKBOOK_STORAGE_PATH",
        "MASTER_WORKBOOK_BUCKET",
        "DOCUMENTS_BUCKET",
    )
    return {k: get_setting(k) for k in keys if get_setting(k)}
