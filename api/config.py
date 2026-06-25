"""Load Supabase credentials from environment or Streamlit secrets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


def _read_streamlit_secrets() -> dict[str, Any]:
    root = Path(__file__).resolve().parent.parent
    path = root / ".streamlit" / "secrets.toml"
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_setting(key: str, default: str = "") -> str:
    env = os.environ.get(key)
    if env:
        return env.strip()
    secrets = _read_streamlit_secrets()
    val = secrets.get(key)
    if val is None:
        return default
    return str(val).strip()


def supabase_url() -> str:
    return get_setting("SUPABASE_URL")


def supabase_anon_key() -> str:
    return get_setting("SUPABASE_ANON_KEY")


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
