"""Audit log routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client

import database as db
import org
from api.deps import get_active_member_client

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/org")
def list_org_audit(
    client: Annotated[Client, Depends(get_active_member_client)],
    limit: Annotated[int, Query(ge=50, le=2000)] = 200,
) -> list[dict[str, Any]]:
    org_id = org.sync_org_context(client)
    if not (org.is_org_admin(client, org_id) or org.can_approve_members(client, org_id)):
        raise HTTPException(status_code=403, detail="Insufficient permissions.")
    try:
        return org.fetch_audit_logs(client, org_id, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/sign-ins")
def list_sign_in_audit(
    client: Annotated[Client, Depends(get_active_member_client)],
    limit: Annotated[int, Query(ge=50, le=2000)] = 500,
) -> list[dict[str, Any]]:
    org_id = org.sync_org_context(client)
    if not (org.is_org_admin(client, org_id) or org.can_approve_members(client, org_id)):
        raise HTTPException(status_code=403, detail="Insufficient permissions.")
    try:
        return db.fetch_audit_sign_ins(client, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
