"""Organization settings routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from supabase import Client

import database as db
import org
from api.deps import get_active_member_client, request_meta
from services.roles import is_lead_accountant, resolve_view_role

router = APIRouter(prefix="/api/org", tags=["org-settings"])


class TransferOwnershipRequest(BaseModel):
    new_owner_user_id: str = Field(min_length=1)


def _can_access_org_settings(client: Client, org_id: str) -> bool:
    if org.is_org_admin(client, org_id) or org.can_view_join_code(client, org_id):
        return True
    try:
        uid = db.get_current_user_id(client)
        row = client.table("organizations").select("owner_user_id").eq("id", org_id).limit(1).execute()
        if row.data and str(row.data[0].get("owner_user_id")) == uid:
            return True
    except Exception:
        pass
    return False


@router.get("/settings")
def get_org_settings(
    client: Annotated[Client, Depends(get_active_member_client)],
) -> dict[str, Any]:
    org_id = org.sync_org_context(client)
    if not _can_access_org_settings(client, org_id):
        raise HTTPException(status_code=403, detail="Insufficient permissions.")
    org_row = org.fetch_organization(client, org_id)
    if not org_row:
        raise HTTPException(status_code=404, detail="Organization not found")
    mem = org.fetch_active_membership(client, org_id)
    org_role = str((mem or {}).get("org_role") or "").lower()
    is_owner = org_role == "owner"
    if not is_owner:
        try:
            uid = db.get_current_user_id(client)
            is_owner = str(org_row.get("owner_user_id")) == uid
        except Exception:
            pass
    out: dict[str, Any] = {
        "id": org_id,
        "name": org_row.get("name"),
        "is_owner": is_owner,
    }
    if org.can_view_join_code(client, org_id) or is_owner:
        out["join_code"] = org_row.get("join_code")
    if is_owner:
        try:
            members = org.list_org_members(client, org_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        uid = None
        try:
            uid = db.get_current_user_id(client)
        except Exception:
            pass
        out["transfer_candidates"] = [
            {
                "user_id": m.get("user_id"),
                "email": (m.get("profiles") or {}).get("email"),
                "org_role": m.get("org_role"),
            }
            for m in members
            if str(m.get("status")) == "active"
            and str(m.get("user_id")) != uid
            and str(m.get("org_role")) != "owner"
        ]
    try:
        legacy = db.fetch_user_role(client)
    except Exception:
        legacy = None
    view_role = resolve_view_role(legacy_role=legacy, org_role=org_role)
    lead = is_lead_accountant(
        view_role=view_role,
        org_role=org_role,
        can_approve=bool((mem or {}).get("can_approve")),
        legacy_role=legacy,
    )
    if lead or is_owner or org.is_org_admin(client, org_id):
        try:
            members = org.list_org_members(client, org_id)
            out["accountants"] = [
                {
                    "user_id": m.get("user_id"),
                    "email": (m.get("profiles") or {}).get("email"),
                    "job_title": m.get("job_title"),
                    "is_lead": bool(m.get("can_approve")),
                }
                for m in members
                if str(m.get("status")) == "active"
                and str(m.get("org_role")) == "accountant"
            ]
        except Exception:
            out["accountants"] = []
    return out


@router.post("/transfer-ownership")
def transfer_ownership(
    body: TransferOwnershipRequest,
    client: Annotated[Client, Depends(get_active_member_client)],
    meta: Annotated[tuple[str | None, str | None], Depends(request_meta)],
) -> dict[str, str]:
    org_id = org.sync_org_context(client)
    mem = org.fetch_active_membership(client, org_id)
    is_owner = bool(mem and str(mem.get("org_role")) == "owner")
    if not is_owner:
        org_row = org.fetch_organization(client, org_id)
        try:
            uid = db.get_current_user_id(client)
            is_owner = bool(org_row and str(org_row.get("owner_user_id")) == uid)
        except Exception:
            is_owner = False
    if not is_owner:
        raise HTTPException(status_code=403, detail="Only the owner can transfer ownership.")
    ua, ip = meta
    try:
        org.transfer_ownership(
            client,
            org_id=org_id,
            new_owner_user_id=body.new_owner_user_id,
            client_ip=ip,
            user_agent=ua,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "transferred"}
