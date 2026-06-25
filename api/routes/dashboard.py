"""Dashboard API routes."""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

from api.config import streamlit_secrets_dict
from api.deps import get_active_member_client
from api.permissions import require_dashboard
from services.dashboard import build_dashboard_payload

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def get_dashboard(
    client: Annotated[Client, Depends(get_active_member_client)],
    currencies: Annotated[Optional[str], Query(description="Comma-separated ISO codes")] = None,
    currency_view: Annotated[str, Query(description="original or usd")] = "original",
) -> dict[str, Any]:
    require_dashboard(client)
    ccy_list = None
    if currencies:
        ccy_list = [c.strip().upper() for c in currencies.split(",") if c.strip()]

    try:
        return build_dashboard_payload(
            client,
            streamlit_secrets_dict(),
            currencies=ccy_list,
            currency_view=currency_view,
        )
    except Exception as exc:
        detail = str(exc).strip() or "Could not load dashboard"
        raise HTTPException(status_code=500, detail=detail) from exc
