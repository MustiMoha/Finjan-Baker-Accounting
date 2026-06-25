"""Organization member management routes."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from supabase import Client

import database as db
import org
from api.deps import get_active_member_client, request_meta

router = APIRouter(prefix="/api/members", tags=["members"])


class ApproveMemberRequest(BaseModel):
    org_role: Literal["user", "accountant", "admin"] = "user"
    can_approve: bool = False


class UpdateMemberRequest(BaseModel):
    org_role: Literal["admin", "accountant", "user"] | None = None
    can_approve: bool | None = None


@router.get("")
def list_members(
    client: Annotated[Client, Depends(get_active_member_client)],
) -> list[dict[str, Any]]:
    org_id = org.sync_org_context(client)
    if not org.is_org_admin(client, org_id):
        raise HTTPException(status_code=403, detail="Organization admin access required.")
    try:
        return org.list_org_members(client, org_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/pending")
def list_pending_members(
    client: Annotated[Client, Depends(get_active_member_client)],
) -> list[dict[str, Any]]:
    org_id = org.sync_org_context(client)
    if not org.can_approve_members(client, org_id):
        raise HTTPException(status_code=403, detail="Member approval permission required.")
    return org.list_pending_members(client, org_id)


@router.post("/pending/{member_id}/approve")
def approve_pending_member(
    member_id: str,
    body: ApproveMemberRequest,
    client: Annotated[Client, Depends(get_active_member_client)],
    meta: Annotated[tuple[str | None, str | None], Depends(request_meta)],
) -> dict[str, str]:
    org_id = org.sync_org_context(client)
    if not org.can_approve_members(client, org_id):
        raise HTTPException(status_code=403, detail="Member approval permission required.")
    ua, ip = meta
    try:
        org.approve_member(
            client,
            member_id=member_id,
            org_id=org_id,
            org_role=body.org_role,
            can_approve=body.can_approve,
            client_ip=ip,
            user_agent=ua,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "approved"}


@router.post("/pending/{member_id}/reject")
def reject_pending_member(
    member_id: str,
    client: Annotated[Client, Depends(get_active_member_client)],
    meta: Annotated[tuple[str | None, str | None], Depends(request_meta)],
) -> dict[str, str]:
    org_id = org.sync_org_context(client)
    if not org.can_approve_members(client, org_id):
        raise HTTPException(status_code=403, detail="Member approval permission required.")
    ua, ip = meta
    try:
        org.reject_member(
            client,
            member_id=member_id,
            org_id=org_id,
            client_ip=ip,
            user_agent=ua,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "rejected"}


@router.patch("/{member_id}")
def update_member(
    member_id: str,
    body: UpdateMemberRequest,
    client: Annotated[Client, Depends(get_active_member_client)],
    meta: Annotated[tuple[str | None, str | None], Depends(request_meta)],
) -> dict[str, str]:
    org_id = org.sync_org_context(client)
    if not org.is_org_admin(client, org_id):
        raise HTTPException(status_code=403, detail="Organization admin access required.")
    ua, ip = meta
    uid_self = db.get_current_user_id(client)
    try:
        if body.org_role is not None:
            org.set_member_org_role(
                client,
                member_id=member_id,
                org_id=org_id,
                org_role=body.org_role,
                client_ip=ip,
                user_agent=ua,
            )
            members = org.list_org_members(client, org_id)
            target = next((m for m in members if str(m.get("id")) == member_id), None)
            if target and str(target.get("user_id")) == uid_self:
                org.sync_legacy_user_role(client, body.org_role)
        if body.can_approve is not None:
            org.set_member_can_approve(
                client,
                member_id=member_id,
                org_id=org_id,
                can_approve=body.can_approve,
                client_ip=ip,
                user_agent=ua,
            )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "updated"}
