"""Streamlit session handoff (one-time codes)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from supabase import Client

from api.config import streamlit_url
from api.deps import get_authenticated_client, get_bearer_token, get_refresh_token
from api.streamlit_handoff import consume_handoff_code, mint_handoff_code

router = APIRouter(prefix="/api/streamlit", tags=["streamlit"])


class HandoffCreateResponse(BaseModel):
    code: str
    url: str


class HandoffExchangeResponse(BaseModel):
    access_token: str
    refresh_token: str


@router.post("/handoff", response_model=HandoffCreateResponse)
def create_streamlit_handoff(
    client: Annotated[Client, Depends(get_authenticated_client)],
    access: Annotated[str, Depends(get_bearer_token)],
    refresh: Annotated[str, Depends(get_refresh_token)],
) -> HandoffCreateResponse:
    access_token = access
    refresh_token = refresh
    code = mint_handoff_code(access_token, refresh_token)
    base = streamlit_url().rstrip("/")
    return HandoffCreateResponse(code=code, url=f"{base}/?handoff_code={code}")


@router.get("/exchange", response_model=HandoffExchangeResponse)
def exchange_streamlit_handoff(
    code: Annotated[str, Query(min_length=8, max_length=128)],
) -> HandoffExchangeResponse:
    row = consume_handoff_code(code)
    if not row:
        raise HTTPException(status_code=404, detail="Handoff code invalid or expired")
    access, refresh = row
    return HandoffExchangeResponse(access_token=access, refresh_token=refresh)
