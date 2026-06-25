"""FastAPI dependencies — authenticated Supabase client."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException
from supabase import Client, create_client

import database as db
import org
from api.config import supabase_anon_key, supabase_url


def get_bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    return token


def get_refresh_token(
    x_refresh_token: Annotated[str | None, Header(alias="X-Refresh-Token")] = None,
) -> str:
    refresh = (x_refresh_token or "").strip()
    if not refresh:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    return refresh


def get_authenticated_client(
    token: Annotated[str, Depends(get_bearer_token)],
    refresh: Annotated[str, Depends(get_refresh_token)],
) -> Client:
    url = supabase_url()
    key = supabase_anon_key()
    if not url or not key:
        raise HTTPException(status_code=503, detail="Supabase is not configured on the server")
    client = create_client(url, key)
    try:
        # Never refresh here — only the React app may rotate refresh tokens.
        active_at, _active_rt = db.bind_session_tokens(
            client, token, refresh, allow_refresh=False
        )
        user = client.auth.get_user(active_at)
        if user is None or user.user is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
    except HTTPException:
        raise
    except ValueError as exc:
        if "expired" in str(exc).lower():
            raise HTTPException(status_code=401, detail="Access token expired") from exc
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    org.set_current_org_id(None)
    return client


def get_active_member_client(
    client: Annotated[Client, Depends(get_authenticated_client)],
) -> Client:
    org.set_current_org_id(None)
    gate = org.resolve_membership_gate(client)
    if gate != "active":
        raise HTTPException(status_code=403, detail="Active organization membership required.")
    oid = org.try_get_current_org_id() or org.org_id_from_client(client)
    if not oid:
        mem = org.fetch_active_membership(client)
        if mem and mem.get("org_id"):
            oid = str(mem["org_id"])
    if not oid:
        raise HTTPException(status_code=500, detail="Organization context missing.")
    org.bind_org_to_client(client, oid)
    return client


def request_meta(
    user_agent: Annotated[str | None, Header(alias="User-Agent")] = None,
    x_forwarded_for: Annotated[str | None, Header(alias="X-Forwarded-For")] = None,
    x_real_ip: Annotated[str | None, Header(alias="X-Real-Ip")] = None,
) -> tuple[str | None, str | None]:
    ua = (user_agent or "")[:2000] or None
    ip = None
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()[:128]
    elif x_real_ip:
        ip = x_real_ip.strip()[:128]
    return ua, ip
