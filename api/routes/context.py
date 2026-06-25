"""App context API — permissions and org info for the JS shell."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client

from api.config import streamlit_secrets_dict
from api.deps import get_active_member_client
from services.app_context import build_app_context

router = APIRouter(prefix="/api/app", tags=["app"])


@router.get("/context")
def get_app_context(
    client: Annotated[Client, Depends(get_active_member_client)],
) -> dict[str, Any]:
    try:
        return build_app_context(client, secrets=streamlit_secrets_dict())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        detail = str(exc).strip() or "Could not load app context"
        raise HTTPException(status_code=500, detail=detail) from exc
