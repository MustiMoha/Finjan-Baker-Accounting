"""Application context for the JS shell — permissions, org, nav gating."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from supabase import Client

import database as db
import org
from services.onboarding_setup import needs_org_setup
from services.roles import build_permissions, resolve_view_role


def _legacy_role(client: Client) -> Optional[str]:
    try:
        return db.fetch_user_role(client)
    except Exception:
        return None


def build_app_context(client: Client, *, secrets: Mapping[str, Any] | None = None) -> dict[str, Any]:
    org.sync_org_context(client)
    org_id = org.get_current_org_id(client)
    mem = org.fetch_active_membership(client, org_id)
    org_row = org.fetch_organization(client, org_id) or {}
    legacy = _legacy_role(client)
    org_role = str((mem or {}).get("org_role") or "")
    can_approve = bool((mem or {}).get("can_approve"))

    view_role = resolve_view_role(legacy_role=legacy, org_role=org_role)

    join_code = None
    try:
        if org.can_view_join_code(client, org_id):
            join_code = org_row.get("join_code")
    except Exception:
        pass

    email = db.get_current_user_email(client)
    profile = db.fetch_user_profile(client)
    full_name = (profile or {}).get("full_name") if profile else None

    pending_members = 0
    pending_entries = 0
    try:
        pending_members = org.count_pending_approvals(client, org_id)
    except Exception:
        pass
    try:
        pending_entries = db.count_pending_transactions(client, status="pending")
    except Exception:
        pass

    is_org_admin = False
    can_view_join_code = False
    can_approve_members_flag = False
    try:
        is_org_admin = org.is_org_admin(client, org_id)
        can_view_join_code = org.can_view_join_code(client, org_id)
        can_approve_members_flag = org.can_approve_members(client, org_id)
    except Exception:
        pass

    permissions = build_permissions(
        view_role=view_role,
        org_role=org_role,
        can_approve=can_approve,
        legacy_role=legacy,
        is_org_admin=is_org_admin,
        can_view_join_code=can_view_join_code,
        can_approve_members_flag=can_approve_members_flag,
        pending_member_count=pending_members,
        pending_entry_count=pending_entries,
    )

    display_currency = "USD"
    try:
        display_currency = db.fetch_display_currency_iso(client)
    except Exception:
        pass

    setup_required = False
    if secrets is not None:
        try:
            setup_required = needs_org_setup(client, secrets)
        except Exception:
            setup_required = False

    return {
        "email": email,
        "full_name": full_name,
        "legacy_role": legacy,
        "view_role": view_role,
        "setup_required": setup_required,
        "org": {
            "id": org_id,
            "name": org_row.get("name"),
            "join_code": join_code,
        },
        "membership": {
            "org_role": org_role,
            "job_title": (mem or {}).get("job_title"),
            "can_approve": can_approve,
            "is_lead_accountant": permissions["is_lead_accountant"],
            "is_owner": permissions.get("is_owner", org_role.lower() == "owner"),
        },
        "permissions": permissions,
        "display_currency": display_currency,
        "home_path": "/accountant" if view_role == "accountant" else "/dashboard",
    }
