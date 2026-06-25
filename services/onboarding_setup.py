"""Post-org setup: choose app role and upload initial workbook."""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional

from supabase import Client

import database as db
import org
import supabase_storage_workbook as sbw

ViewRole = Literal["admin", "accountant", "viewer"]

_VIEW_TO_LEGACY: dict[str, str] = {
    "admin": "admin",
    "accountant": "staff",
    "viewer": "auditor",
}


def needs_org_setup(client: Client, secrets: Mapping[str, Any]) -> bool:
    org.sync_org_context(client)
    gate = org.resolve_membership_gate(client)
    if gate != "active":
        return False

    doc = db.fetch_onboarding_json(client)
    if doc.get("setup_completed"):
        return False

    mem = org.fetch_active_membership(client, org.get_current_org_id(client))
    if not mem:
        return False

    legacy = None
    try:
        legacy = db.fetch_user_role(client)
    except Exception:
        pass

    path_secret = str(secrets.get("MASTER_WORKBOOK_STORAGE_PATH") or "").strip()
    try:
        workbook = db.resolve_master_workbook_file_id(client, path_secret)
    except Exception:
        workbook = ""

    if legacy and str(workbook or "").strip():
        return False

    org_role = str(mem.get("org_role") or "").lower()
    if org_role in ("owner", "admin"):
        return True
    if legacy is None:
        return True
    return not bool(str(workbook or "").strip())


def complete_org_setup(
    client: Client,
    *,
    view_role: ViewRole,
    secrets: Mapping[str, Any],
    workbook_bytes: Optional[bytes] = None,
    workbook_filename: Optional[str] = None,
    skip_workbook: bool = False,
) -> dict[str, Any]:
    org.sync_org_context(client)
    gate = org.resolve_membership_gate(client)
    if gate != "active":
        raise ValueError("Active organization membership required.")

    legacy = _VIEW_TO_LEGACY.get(view_role)
    if not legacy:
        raise ValueError("Invalid role selection.")

    uid = db.get_current_user_id(client)
    db.update_user_role(client, uid, legacy)

    org_id = org.get_current_org_id(client)
    mem = org.fetch_active_membership(client, org_id)
    org_role = str((mem or {}).get("org_role") or "")

    if workbook_bytes:
        if not org.can_upload_initial_workbook(client, org_id) and not org.can_replace_workbook(
            client, org_id
        ):
            raise ValueError("You do not have permission to upload a workbook.")
        hint = workbook_filename or "accounting_master.xlsx"
        bucket = sbw.master_workbook_bucket(secrets)
        op = org.master_workbook_path_for_org(org_id, hint)
        sbw.upload_master_bytes(client, bucket, op, workbook_bytes, filename_hint=hint)
        db.update_master_workbook_file_id(client, op)
    elif not skip_workbook:
        path_secret = str(secrets.get("MASTER_WORKBOOK_STORAGE_PATH") or "").strip()
        existing = db.resolve_master_workbook_file_id(client, path_secret)
        if not existing.strip() and org_role in ("owner", "admin"):
            raise ValueError("Upload a workbook or choose Skip for now.")

    doc = {
        "setup_completed": True,
        "chosen_view_role": view_role,
        "workbook_skipped": bool(skip_workbook and not workbook_bytes),
    }
    db.update_onboarding_json(client, doc)
    return doc
