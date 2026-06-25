"""Multi-tenant organization context, membership, permissions, and audit helpers."""

from __future__ import annotations

import json
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from supabase import Client

import database as db

OrgRole = Literal["owner", "admin", "accountant", "user"]
MemberStatus = Literal["pending", "active", "rejected"]

_current_org_id: ContextVar[Optional[str]] = ContextVar("_current_org_id", default=None)


_BAKER_ORG_ATTR = "_baker_org_id"


def set_current_org_id(org_id: Optional[str]) -> None:
    _current_org_id.set((org_id or "").strip() or None)


def bind_org_to_client(client: Client, org_id: str) -> None:
    oid = (org_id or "").strip()
    if not oid:
        return
    setattr(client, _BAKER_ORG_ATTR, oid)
    set_current_org_id(oid)


def org_id_from_client(client: Client) -> Optional[str]:
    raw = getattr(client, _BAKER_ORG_ATTR, None)
    return str(raw).strip() if raw else None


def sync_org_context(client: Client) -> str:
    """Bind org id for this thread — safe across FastAPI threadpool workers."""
    bound = org_id_from_client(client)
    if bound:
        set_current_org_id(bound)
        return bound
    gate = resolve_membership_gate(client)
    if gate != "active":
        raise RuntimeError("Active organization membership required")
    oid = try_get_current_org_id()
    if not oid:
        raise RuntimeError("No organization selected")
    bind_org_to_client(client, oid)
    return oid


def get_current_org_id(client: Client | None = None) -> str:
    if client is not None:
        return sync_org_context(client)
    oid = try_get_current_org_id()
    if oid:
        return oid
    raise RuntimeError("No organization selected")


def try_get_current_org_id(client: Client | None = None) -> Optional[str]:
    if client is not None:
        bound = org_id_from_client(client)
        if bound:
            set_current_org_id(bound)
            return bound
    return _current_org_id.get()


def org_role_to_legacy_role(org_role: str) -> str:
    """Map org role → legacy user_roles value for existing RLS helpers."""
    r = (org_role or "").strip().lower()
    if r in ("owner", "admin"):
        return "admin"
    if r == "accountant":
        return "staff"
    return "auditor"


def sync_legacy_user_role(client: Client, org_role: str) -> None:
    client.rpc("sync_legacy_user_role_from_org", {"p_org_role": org_role}).execute()


def log_audit_event(
    client: Client,
    *,
    action: str,
    org_id: Optional[str] = None,
    target_user_id: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    success: bool = True,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    try:
        uid = db.get_current_user_id(client)
    except Exception:
        uid = None
    payload: dict[str, Any] = {
        "org_id": org_id or try_get_current_org_id(),
        "actor_user_id": uid,
        "action": action[:128],
        "target_user_id": target_user_id,
        "details": details or {},
        "success": bool(success),
        "client_ip": (client_ip or "")[:128] or None,
        "user_agent": (user_agent or "")[:2000] or None,
    }
    try:
        client.table("audit_logs").insert(payload).execute()
    except Exception:
        pass


def fetch_user_memberships(client: Client) -> list[dict[str, Any]]:
    uid = db.get_current_user_id(client)
    q = (
        client.table("org_members")
        .select("id,org_id,org_role,job_title,status,can_approve,requested_at,organizations(id,name,join_code,owner_user_id)")
        .eq("user_id", uid)
        .order("created_at", desc=True)
        .execute()
    )
    return q.data or []


def fetch_active_membership(client: Client, org_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    oid = org_id or try_get_current_org_id()
    uid = db.get_current_user_id(client)
    q = client.table("org_members").select("*").eq("user_id", uid).eq("status", "active")
    if oid:
        q = q.eq("org_id", oid)
    rows = q.order("created_at", desc=True).execute()
    if not rows.data:
        return None
    if len(rows.data) == 1:
        return rows.data[0]
    for row in rows.data:
        if str(row.get("org_role")) == "owner":
            return row
    return rows.data[0]


def fetch_membership_any_status(client: Client) -> Optional[dict[str, Any]]:
    uid = db.get_current_user_id(client)
    row = (
        client.table("org_members")
        .select("*,organizations(id,name,join_code,owner_user_id)")
        .eq("user_id", uid)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not row.data:
        return None
    return row.data[0]


def fetch_organization(client: Client, org_id: str) -> Optional[dict[str, Any]]:
    row = client.table("organizations").select("*").eq("id", org_id).limit(1).execute()
    if not row.data:
        return None
    return row.data[0]


def create_organization(
    client: Client,
    *,
    name: str,
    job_title: str,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict[str, Any]:
    uid = db.get_current_user_id(client)
    nm = name.strip()
    if len(nm) < 2:
        raise ValueError("Organization name must be at least 2 characters.")
    jt = job_title.strip()
    if not jt:
        raise ValueError("Enter your role title (e.g. CFO, Controller).")

    existing = (
        client.table("org_members")
        .select("id")
        .eq("user_id", uid)
        .in_("status", ["active", "pending"])
        .limit(1)
        .execute()
    )
    if existing.data:
        raise ValueError("You already belong to an organization or have a pending request.")

    rpc = client.rpc(
        "create_organization_with_owner",
        {"p_name": nm, "p_job_title": jt},
    ).execute()
    if not rpc.data:
        raise ValueError("Failed to create organization.")
    org_row = rpc.data[0] if isinstance(rpc.data, list) else rpc.data
    if isinstance(org_row, str):
        org_row = json.loads(org_row)
    org_id = str(org_row["id"])

    set_current_org_id(org_id)
    log_audit_event(
        client,
        action="org.created",
        org_id=org_id,
        details={"name": nm, "join_code": org_row.get("join_code")},
        client_ip=client_ip,
        user_agent=user_agent,
    )
    return org_row


def request_join_organization(
    client: Client,
    *,
    join_code: str,
    job_title: str,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict[str, Any]:
    uid = db.get_current_user_id(client)
    code = join_code.strip().upper()
    if len(code) != 6 or not code.isalnum():
        raise ValueError("Enter a valid 6-character join code.")
    jt = job_title.strip()
    if not jt:
        raise ValueError("Enter your role title.")

    pending = (
        client.table("org_members")
        .select("id")
        .eq("user_id", uid)
        .in_("status", ["active", "pending"])
        .limit(1)
        .execute()
    )
    if pending.data:
        raise ValueError("You already have an active or pending membership.")

    rpc = client.rpc(
        "request_join_organization_by_code",
        {"p_join_code": code, "p_job_title": jt},
    ).execute()
    if not rpc.data:
        raise ValueError("Could not submit join request.")
    row = rpc.data[0] if isinstance(rpc.data, list) else rpc.data
    if isinstance(row, str):
        row = json.loads(row)
    org_id = str(row.get("org_id") or "")

    log_audit_event(
        client,
        action="member.join_requested",
        org_id=org_id or None,
        target_user_id=uid,
        details={"job_title": jt},
        client_ip=client_ip,
        user_agent=user_agent,
    )
    return row


def _attach_profile_emails(client: Client, members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not members:
        return []
    user_ids = list({str(m["user_id"]) for m in members if m.get("user_id")})
    if not user_ids:
        return members
    try:
        prof = client.table("profiles").select("id,email,full_name").in_("id", user_ids).execute()
    except Exception:
        return members
    by_id = {str(p["id"]): p for p in (prof.data or []) if p.get("id")}
    out: list[dict[str, Any]] = []
    for m in members:
        row = dict(m)
        uid = str(m.get("user_id") or "")
        p = by_id.get(uid)
        row["profiles"] = (
            {"email": p.get("email"), "full_name": p.get("full_name")} if p else None
        )
        out.append(row)
    return out


def list_pending_members(client: Client, org_id: str) -> list[dict[str, Any]]:
    if not can_approve_members(client, org_id):
        raise PermissionError("You cannot approve members for this organization.")
    q = (
        client.table("org_members")
        .select("id,user_id,job_title,requested_at")
        .eq("org_id", org_id)
        .eq("status", "pending")
        .order("requested_at")
        .execute()
    )
    return _attach_profile_emails(client, q.data or [])


def list_org_members(client: Client, org_id: str) -> list[dict[str, Any]]:
    q = (
        client.table("org_members")
        .select("id,user_id,org_role,job_title,status,can_approve")
        .eq("org_id", org_id)
        .order("org_role")
        .execute()
    )
    return _attach_profile_emails(client, q.data or [])


def approve_member(
    client: Client,
    *,
    member_id: str,
    org_id: str,
    org_role: OrgRole = "user",
    can_approve: bool = False,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    if not can_approve_members(client, org_id):
        raise PermissionError("Not allowed to approve members.")
    reviewer = db.get_current_user_id(client)
    now = datetime.now(timezone.utc).isoformat()
    update_payload: dict[str, Any] = {
        "status": "active",
        "org_role": org_role,
        "reviewed_by": reviewer,
        "reviewed_at": now,
        "updated_at": now,
    }
    if org_role == "accountant":
        update_payload["can_approve"] = bool(can_approve)
    row = (
        client.table("org_members")
        .update(update_payload)
        .eq("id", member_id)
        .eq("org_id", org_id)
        .eq("status", "pending")
        .execute()
    )
    if not row.data:
        raise ValueError("Member request not found or already processed.")
    target = str(row.data[0]["user_id"])
    log_audit_event(
        client,
        action="member.approved",
        org_id=org_id,
        target_user_id=target,
        details={"org_role": org_role, "member_id": member_id},
        client_ip=client_ip,
        user_agent=user_agent,
    )


def reject_member(
    client: Client,
    *,
    member_id: str,
    org_id: str,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    if not can_approve_members(client, org_id):
        raise PermissionError("Not allowed to reject members.")
    reviewer = db.get_current_user_id(client)
    now = datetime.now(timezone.utc).isoformat()
    row = (
        client.table("org_members")
        .update(
            {
                "status": "rejected",
                "reviewed_by": reviewer,
                "reviewed_at": now,
                "updated_at": now,
            }
        )
        .eq("id", member_id)
        .eq("org_id", org_id)
        .eq("status", "pending")
        .execute()
    )
    if not row.data:
        raise ValueError("Member request not found or already processed.")
    target = str(row.data[0]["user_id"])
    log_audit_event(
        client,
        action="member.rejected",
        org_id=org_id,
        target_user_id=target,
        details={"member_id": member_id},
        client_ip=client_ip,
        user_agent=user_agent,
    )


def set_member_can_approve(
    client: Client,
    *,
    member_id: str,
    org_id: str,
    can_approve: bool,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    if not is_org_admin(client, org_id):
        raise PermissionError("Only admins can delegate approval power.")
    mem = (
        client.table("org_members")
        .select("id,user_id,org_role")
        .eq("id", member_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not mem.data:
        raise ValueError("Member not found.")
    target = mem.data[0]
    if str(target.get("org_role")) == "owner":
        raise ValueError("Owner always has approval power; cannot change.")
    client.table("org_members").update(
        {"can_approve": bool(can_approve), "updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", member_id).execute()
    log_audit_event(
        client,
        action="member.can_approve_changed",
        org_id=org_id,
        target_user_id=str(target["user_id"]),
        details={"can_approve": bool(can_approve)},
        client_ip=client_ip,
        user_agent=user_agent,
    )


def set_member_org_role(
    client: Client,
    *,
    member_id: str,
    org_id: str,
    org_role: OrgRole,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    if not is_org_admin(client, org_id):
        raise PermissionError("Only admins can change member roles.")
    if org_role == "owner":
        raise ValueError("Use Transfer Ownership to assign a new owner.")
    mem = (
        client.table("org_members")
        .select("id,user_id,org_role,status")
        .eq("id", member_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not mem.data:
        raise ValueError("Member not found.")
    target = mem.data[0]
    if str(target.get("org_role")) == "owner":
        raise ValueError("Cannot change the owner's role here — transfer ownership first.")
    if str(target.get("status")) != "active":
        raise ValueError("Only active members can be reassigned.")
    client.table("org_members").update(
        {"org_role": org_role, "updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", member_id).execute()
    log_audit_event(
        client,
        action="member.role_changed",
        org_id=org_id,
        target_user_id=str(target["user_id"]),
        details={"org_role": org_role, "member_id": member_id},
        client_ip=client_ip,
        user_agent=user_agent,
    )


def transfer_ownership(
    client: Client,
    *,
    org_id: str,
    new_owner_user_id: str,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    org = fetch_organization(client, org_id)
    if not org:
        raise ValueError("Organization not found.")
    uid = db.get_current_user_id(client)
    if str(org.get("owner_user_id")) != uid:
        raise PermissionError("Only the current owner can transfer ownership.")

    new_mem = (
        client.table("org_members")
        .select("id,org_role,status")
        .eq("org_id", org_id)
        .eq("user_id", new_owner_user_id)
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if not new_mem.data:
        raise ValueError("New owner must be an active member.")

    now = datetime.now(timezone.utc).isoformat()
    client.table("organizations").update(
        {"owner_user_id": new_owner_user_id, "updated_at": now}
    ).eq("id", org_id).execute()

    client.table("org_members").update(
        {"org_role": "admin", "can_approve": True, "updated_at": now}
    ).eq("org_id", org_id).eq("user_id", uid).execute()

    client.table("org_members").update(
        {"org_role": "owner", "can_approve": True, "updated_at": now}
    ).eq("id", new_mem.data[0]["id"]).execute()

    log_audit_event(
        client,
        action="org.ownership_transferred",
        org_id=org_id,
        target_user_id=new_owner_user_id,
        client_ip=client_ip,
        user_agent=user_agent,
    )


def is_org_owner(client: Client, org_id: str) -> bool:
    mem = fetch_active_membership(client, org_id)
    return bool(mem and str(mem.get("org_role")) == "owner")


def is_org_admin(client: Client, org_id: str) -> bool:
    mem = fetch_active_membership(client, org_id)
    return bool(mem and str(mem.get("org_role")) in ("owner", "admin"))


def can_approve_members(client: Client, org_id: str) -> bool:
    mem = fetch_active_membership(client, org_id)
    if not mem:
        return False
    if str(mem.get("org_role")) == "owner":
        return True
    return bool(mem.get("can_approve"))


def can_view_join_code(client: Client, org_id: str) -> bool:
    return is_org_owner(client, org_id) or can_approve_members(client, org_id)


def can_upload_initial_workbook(client: Client, org_id: str) -> bool:
    return is_org_owner(client, org_id)


def can_replace_workbook(client: Client, org_id: str) -> bool:
    mem = fetch_active_membership(client, org_id)
    if not mem:
        return False
    return str(mem.get("org_role")) in ("owner", "admin", "accountant")


def org_storage_prefix(org_id: str) -> str:
    return f"orgs/{org_id.strip()}"


def master_workbook_path_for_org(org_id: str, filename: str = "accounting_master.xlsx") -> str:
    safe = filename.strip().replace("\\", "/").lstrip("/")
    return f"{org_storage_prefix(org_id)}/master/{safe}"


def count_pending_approvals(client: Client, org_id: str) -> int:
    if not can_approve_members(client, org_id):
        return 0
    q = (
        client.table("org_members")
        .select("id", count="exact")
        .eq("org_id", org_id)
        .eq("status", "pending")
        .execute()
    )
    return int(q.count or 0)


def _audit_summary(action: str, details: dict[str, Any]) -> str:
    a = (action or "").strip()
    if a == "entry.submitted":
        who = details.get("submitter_email") or details.get("submitter_user_id") or "User"
        desc = (details.get("description") or "")[:80]
        return f"{who} submitted entry: {desc}"
    if a == "entry.approved":
        who = details.get("approver_email") or details.get("approver_user_id") or "User"
        desc = (details.get("description") or "")[:80]
        return f"{who} approved entry: {desc}"
    if a == "entry.rejected":
        who = details.get("reviewer_email") or details.get("reviewer_user_id") or "User"
        desc = (details.get("description") or "")[:80]
        return f"{who} rejected entry: {desc}"
    if a == "account_buckets.updated":
        who = details.get("actor_email") or "Lead accountant"
        n = details.get("bucket_count")
        m = details.get("mapping_count")
        return f"{who} updated account classification ({n} buckets, {m} rules)"
    if a == "member.approved":
        return f"Member approved as {details.get('org_role', 'user')}"
    if a == "member.role_changed":
        return f"Role changed to {details.get('org_role', '')}"
    if a == "member.can_approve_changed":
        return f"Lead accountant: {'yes' if details.get('can_approve') else 'no'}"
    return a.replace(".", " ").replace("_", " ")


def fetch_audit_logs(client: Client, org_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
    q = (
        client.table("audit_logs")
        .select("id,action,actor_user_id,target_user_id,details,success,client_ip,occurred_at")
        .eq("org_id", org_id)
        .order("occurred_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = q.data or []
    actor_ids = {str(r["actor_user_id"]) for r in rows if r.get("actor_user_id")}
    email_by_uid: dict[str, str] = {}
    if actor_ids:
        try:
            prof = (
                client.table("profiles")
                .select("id,email")
                .in_("id", list(actor_ids))
                .execute()
            )
            for p in prof.data or []:
                if p.get("id") and p.get("email"):
                    email_by_uid[str(p["id"])] = str(p["email"])
        except Exception:
            pass
    out: list[dict[str, Any]] = []
    for r in rows:
        item = dict(r)
        uid = str(r.get("actor_user_id") or "")
        details = r.get("details") if isinstance(r.get("details"), dict) else {}
        item["actor_email"] = email_by_uid.get(uid) or details.get("submitter_email") or details.get("approver_email")
        item["summary"] = _audit_summary(str(r.get("action") or ""), details)
        out.append(item)
    return out


def _ensure_app_settings_row(client: Client, org_id: str) -> None:
    existing = client.table("app_settings").select("org_id").eq("org_id", org_id).limit(1).execute()
    if existing.data:
        return
    uid = db.get_current_user_id(client)
    client.table("app_settings").insert(
        {
            "org_id": org_id,
            "fiscal_year_start_month": 1,
            "updated_by": uid,
        }
    ).execute()


def _try_ensure_owner_membership(client: Client) -> Optional[dict[str, Any]]:
    """Repair missing owner org_members row (common after migrations)."""
    try:
        client.rpc("ensure_owner_org_membership", {}).execute()
    except Exception:
        pass
    try:
        return fetch_active_membership(client)
    except Exception:
        return None


def resolve_membership_gate(client: Client) -> Literal["none", "pending", "rejected", "active"]:
    """Post-login routing: onboarding, waiting, or main app."""
    active: Optional[dict[str, Any]] = None
    try:
        active = fetch_active_membership(client)
    except Exception:
        active = None

    if active:
        set_current_org_id(str(active["org_id"]))
        try:
            sync_legacy_user_role(client, str(active["org_role"]))
        except Exception:
            pass
        return "active"

    active = _try_ensure_owner_membership(client)
    if active:
        set_current_org_id(str(active["org_id"]))
        try:
            sync_legacy_user_role(client, str(active["org_role"]))
        except Exception:
            pass
        return "active"

    mem: Optional[dict[str, Any]] = None
    try:
        mem = fetch_membership_any_status(client)
    except Exception:
        mem = None
    if not mem:
        return "none"
    st = str(mem.get("status") or "")
    if st == "pending":
        active = _try_ensure_owner_membership(client)
        if active:
            set_current_org_id(str(active["org_id"]))
            try:
                sync_legacy_user_role(client, str(active["org_role"]))
            except Exception:
                pass
            return "active"
        return "pending"
    if st == "rejected":
        return "rejected"
    return "none"
