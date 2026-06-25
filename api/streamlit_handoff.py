"""One-time codes to pass Supabase session tokens from Baker → Streamlit without long URLs."""

from __future__ import annotations

import secrets
import time
from typing import Optional

_store: dict[str, tuple[str, str, float]] = {}
_TTL_SEC = 120


def mint_handoff_code(access_token: str, refresh_token: str) -> str:
    now = time.time()
    expired = [k for k, (_, _, exp) in _store.items() if exp <= now]
    for k in expired:
        _store.pop(k, None)

    code = secrets.token_urlsafe(24)
    _store[code] = (access_token, refresh_token, now + _TTL_SEC)
    return code


def consume_handoff_code(code: str) -> Optional[tuple[str, str]]:
    row = _store.pop(str(code or "").strip(), None)
    if not row:
        return None
    access, refresh, exp = row
    if time.time() > exp:
        return None
    return access, refresh
