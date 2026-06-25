"""Role resolution — Admin, Accountant, Viewer (+ lead accountant)."""

from __future__ import annotations

from typing import Any, Literal, Optional

ViewRole = Literal["admin", "accountant", "viewer"]


def resolve_view_role(*, legacy_role: Optional[str], org_role: str) -> ViewRole:
    """UI view role. Org owner keeps chosen onboarding role; owner capabilities use org_role separately."""
    org_key = (org_role or "").strip().lower()
    leg = (legacy_role or "").strip().lower()

    if org_key == "owner":
        if leg == "staff":
            return "accountant"
        if leg == "auditor":
            return "viewer"
        return "admin"

    if org_key == "admin" or leg == "admin":
        return "admin"
    if org_key == "accountant" or leg == "staff":
        return "accountant"
    return "viewer"


def is_org_owner(org_role: str) -> bool:
    return (org_role or "").strip().lower() == "owner"


def can_owner_accountant_settings(*, view_role: ViewRole, org_role: str) -> bool:
    """Full Settings page — owners and accountants only (not admin-only users)."""
    org_key = (org_role or "").strip().lower()
    if org_key == "owner":
        return True
    if view_role == "accountant" or org_key == "accountant":
        return True
    return False


can_import_layout = can_owner_accountant_settings


def is_lead_accountant(*, view_role: ViewRole, org_role: str, can_approve: bool, legacy_role: Optional[str]) -> bool:
    org_key = (org_role or "").strip().lower()
    leg = (legacy_role or "").strip().lower()
    if org_key == "owner":
        return True
    if view_role == "admin":
        return True
    if org_key == "admin" or leg == "admin":
        return True
    return view_role == "accountant" and bool(can_approve)


def build_permissions(
    *,
    view_role: ViewRole,
    org_role: str,
    can_approve: bool,
    legacy_role: Optional[str],
    is_org_admin: bool,
    can_view_join_code: bool,
    can_approve_members_flag: bool,
    pending_member_count: int,
    pending_entry_count: int,
) -> dict[str, Any]:
    owner = is_org_owner(org_role)

    lead = is_lead_accountant(
        view_role=view_role,
        org_role=org_role,
        can_approve=can_approve,
        legacy_role=legacy_role,
    )

    can_dashboard = view_role in ("admin", "viewer")
    can_accountant_home = view_role == "accountant"
    can_entries = view_role in ("admin", "accountant")
    can_financials = view_role in ("admin", "accountant")
    can_approvals = view_role == "admin" or (view_role == "accountant" and lead)
    can_settings = can_owner_accountant_settings(view_role=view_role, org_role=org_role)
    can_audit = view_role == "admin" or (view_role == "accountant" and lead) or can_approve_members_flag
    can_org_settings = owner or is_org_admin or can_view_join_code
    can_members = owner or is_org_admin
    can_member_approvals = (owner or view_role == "admin" or lead) and can_approve_members_flag
    can_forecast_config = lead and view_role == "accountant"

    return {
        "view_role": view_role,
        "is_owner": owner,
        "is_lead_accountant": lead,
        "can_dashboard": can_dashboard,
        "can_accountant_home": can_accountant_home,
        "can_entries": can_entries,
        "can_approvals": can_approvals,
        "can_financials": can_financials,
        "can_audit": can_audit and view_role != "viewer",
        "can_org_settings": can_org_settings and view_role != "viewer",
        "can_members": can_members and view_role == "admin",
        "can_member_approvals": can_member_approvals,
        "can_forecast_config": can_forecast_config,
        "can_settings": can_settings,
        "pending_member_count": pending_member_count,
        "pending_entry_count": pending_entry_count,
    }
