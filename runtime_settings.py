"""Shared settings: OS environment (Fly.io/Vercel) with `.streamlit/secrets.toml` fallback."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

_ROOT = Path(__file__).resolve().parent
_SECRETS_PATH = _ROOT / ".streamlit" / "secrets.toml"


def _read_streamlit_secrets_file() -> dict[str, Any]:
    if not _SECRETS_PATH.is_file():
        return {}
    try:
        with _SECRETS_PATH.open("rb") as f:
            data = tomllib.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_setting(key: str, default: str = "") -> str:
    env = os.environ.get(key)
    if env is not None and str(env).strip():
        return str(env).strip()
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            val = st.secrets.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
    except Exception:
        pass
    secrets = _read_streamlit_secrets_file()
    val = secrets.get(key)
    if val is None:
        return default
    return str(val).strip()


def cors_allowed_origins() -> list[str]:
    """Browser origins allowed to call the API (Vercel app + local dev)."""
    origins: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        u = (url or "").strip().rstrip("/")
        if not u or u in seen:
            return
        seen.add(u)
        origins.append(u)

    raw = get_setting("CORS_ALLOWED_ORIGINS", "")
    if raw:
        for part in raw.replace(";", ",").split(","):
            add(part.strip())
    add(get_setting("AUTH_WEB_URL", "http://127.0.0.1:8000"))
    for local in (
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ):
        add(local)
    return origins


def serve_auth_ui() -> bool:
    """When false, API is API-only (React hosted on Vercel)."""
    flag = get_setting("SERVE_AUTH_UI", "true").strip().casefold()
    return flag not in ("0", "false", "no", "off")
