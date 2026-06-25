"""One-time codes to pass Supabase session tokens from Baker API → Streamlit."""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import Client, create_client

from api.config import supabase_service_role_key, supabase_url

_store: dict[str, tuple[str, str, float]] = {}
_TTL_SEC = 120


def _service_client() -> Optional[Client]:
    url = supabase_url()
    key = supabase_service_role_key()
    if not url or not key:
        return None
    return create_client(url, key)


def _cleanup_memory_store() -> None:
    now = time.time()
    expired = [k for k, (_, _, exp) in _store.items() if exp <= now]
    for k in expired:
        _store.pop(k, None)


def _mint_db(client: Client, access_token: str, refresh_token: str) -> str:
    code = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(seconds=_TTL_SEC)
    client.table("streamlit_handoff_codes").insert(
        {
            "code": code,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires.isoformat(),
        }
    ).execute()
    return code


def _consume_db(client: Client, code: str) -> Optional[tuple[str, str]]:
    now = datetime.now(timezone.utc).isoformat()
    res = (
        client.table("streamlit_handoff_codes")
        .select("code, access_token, refresh_token, expires_at")
        .eq("code", code)
        .gt("expires_at", now)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    row = res.data[0]
    client.table("streamlit_handoff_codes").delete().eq("code", code).execute()
    access = str(row.get("access_token") or "")
    refresh = str(row.get("refresh_token") or "")
    if not access or not refresh:
        return None
    return access, refresh


def mint_handoff_code(access_token: str, refresh_token: str) -> str:
    client = _service_client()
    if client is not None:
        try:
            return _mint_db(client, access_token, refresh_token)
        except Exception:
            pass
    _cleanup_memory_store()
    code = secrets.token_urlsafe(24)
    _store[code] = (access_token, refresh_token, time.time() + _TTL_SEC)
    return code


def consume_handoff_code(code: str) -> Optional[tuple[str, str]]:
    code_s = str(code or "").strip()
    if not code_s:
        return None
    client = _service_client()
    if client is not None:
        try:
            row = _consume_db(client, code_s)
            if row is not None:
                return row
        except Exception:
            pass
    row = _store.pop(code_s, None)
    if not row:
        return None
    access, refresh, exp = row
    if time.time() > exp:
        return None
    return access, refresh
