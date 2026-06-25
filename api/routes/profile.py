"""User profile — display name."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from supabase import Client

import database as db
from api.deps import get_authenticated_client

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("")
def get_profile(
    client: Annotated[Client, Depends(get_authenticated_client)],
) -> dict[str, Any]:
    row = db.fetch_user_profile(client)
    email = db.get_current_user_email(client)
    return {
        "id": db.get_current_user_id(client),
        "email": email,
        "full_name": (row or {}).get("full_name"),
    }


class ProfilePatch(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)


@router.patch("")
def patch_profile(
    body: ProfilePatch,
    client: Annotated[Client, Depends(get_authenticated_client)],
) -> dict[str, Any]:
    try:
        row = db.update_profile_full_name(client, body.full_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    email = db.get_current_user_email(client)
    return {
        "id": row.get("id"),
        "email": email or row.get("email"),
        "full_name": row.get("full_name"),
    }
