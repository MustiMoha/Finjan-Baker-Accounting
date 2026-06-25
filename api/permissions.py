"""Shared API permission checks (actual roles — not UI preview)."""

from __future__ import annotations

from fastapi import HTTPException
from supabase import Client

import database as db
import org
from services.roles import can_owner_accountant_settings, is_lead_accountant, resolve_view_role


def _membership(client: Client) -> tuple[str, bool, str | None]:
    org_id = org.sync_org_context(client)
    mem = org.fetch_active_membership(client, org_id)
    org_role = str((mem or {}).get("org_role") or "")
    can_approve = bool((mem or {}).get("can_approve"))
    legacy = None
    try:
        legacy = db.fetch_user_role(client)
    except Exception:
        pass
    return org_role, can_approve, legacy


def require_entries(client: Client) -> None:
    org_role, _, legacy = _membership(client)
    role = resolve_view_role(legacy_role=legacy, org_role=org_role)
    if role not in ("admin", "accountant"):
        raise HTTPException(status_code=403, detail="Admin or accountant access required.")


def require_dashboard(client: Client) -> None:
    org_role, _, legacy = _membership(client)
    role = resolve_view_role(legacy_role=legacy, org_role=org_role)
    if role not in ("admin", "viewer"):
        raise HTTPException(status_code=403, detail="Dashboard is not available for accountants.")


def require_approvals(client: Client) -> None:
    org_role, can_approve, legacy = _membership(client)
    role = resolve_view_role(legacy_role=legacy, org_role=org_role)
    if role == "admin":
        return
    if role == "accountant" and is_lead_accountant(
        view_role=role, org_role=org_role, can_approve=can_approve, legacy_role=legacy
    ):
        return
    raise HTTPException(status_code=403, detail="Approval permission required.")


def can_use_settings(client: Client) -> bool:
    org_role, _, legacy = _membership(client)
    view = resolve_view_role(legacy_role=legacy, org_role=org_role)
    return can_owner_accountant_settings(view_role=view, org_role=org_role)


def require_lead_accountant(client: Client) -> None:
    """Lead accountant — can approve entries and edit balance-sheet classification."""
    require_approvals(client)


def require_owner_accountant_settings(client: Client) -> None:
    if not can_use_settings(client):
        raise HTTPException(
            status_code=403,
            detail="Settings require owner or accountant access.",
        )
