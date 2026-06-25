#!/usr/bin/env python3
"""Link a Supabase auth user to an organization as owner/admin (service role required)."""

from __future__ import annotations

import argparse
import sys
from typing import Any, Optional

from supabase import Client, create_client

from api.config import get_setting, supabase_url


def _service_client() -> Client:
    url = supabase_url()
    key = get_setting("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.\n"
            "Add the service role key to .streamlit/secrets.toml (Project Settings → API in Supabase)."
        )
    return create_client(url, key)


def _find_user_id(client: Client, email: str) -> str:
    target = email.strip().lower()
    page = 1
    per_page = 200
    while True:
        users = client.auth.admin.list_users(page=page, per_page=per_page)
        if not users:
            break
        for user in users:
            em = (getattr(user, "email", None) or "").strip().lower()
            if em == target:
                return str(user.id)
        if len(users) < per_page:
            break
        page += 1
    sys.exit(f"No auth user found for email: {email}")


def _find_org(client: Client, org_name: str) -> dict[str, Any]:
    exact = client.table("organizations").select("*").eq("name", org_name.strip()).limit(1).execute()
    if exact.data:
        return exact.data[0]
    fuzzy = client.table("organizations").select("*").ilike("name", org_name.strip()).limit(5).execute()
    if not fuzzy.data:
        sys.exit(f"No organization found matching: {org_name}")
    if len(fuzzy.data) > 1:
        names = ", ".join(f'"{r["name"]}"' for r in fuzzy.data)
        sys.exit(f"Multiple organizations match {org_name!r}: {names}. Use the exact name.")
    return fuzzy.data[0]


def _next_app_settings_id(client: Client) -> int:
    row = client.table("app_settings").select("id").order("id", desc=True).limit(1).execute()
    if row.data:
        return int(row.data[0]["id"]) + 1
    return 1


def promote_org_admin(
    client: Client,
    *,
    email: str,
    org_name: str,
    job_title: str = "Administrator",
    make_owner: bool = True,
) -> None:
    uid = _find_user_id(client, email)
    org = _find_org(client, org_name)
    org_id = str(org["id"])

    if make_owner:
        client.table("organizations").update({"owner_user_id": uid}).eq("id", org_id).execute()

    client.table("org_members").upsert(
        {
            "org_id": org_id,
            "user_id": uid,
            "org_role": "owner" if make_owner else "admin",
            "job_title": job_title,
            "status": "active",
            "can_approve": True,
        },
        on_conflict="org_id,user_id",
    ).execute()

    client.table("user_roles").upsert({"user_id": uid, "role": "admin"}, on_conflict="user_id").execute()

    settings = client.table("app_settings").select("id").eq("org_id", org_id).limit(1).execute()
    if not settings.data:
        client.table("app_settings").insert(
            {
                "id": _next_app_settings_id(client),
                "org_id": org_id,
                "fiscal_year_start_month": 1,
                "updated_by": uid,
            }
        ).execute()

    role = "owner" if make_owner else "admin"
    print(f"OK: {email} → {org['name']} ({org_id}) as {role}")
    print(f"    user_id: {uid}")
    print("Sign out and sign in again to load the dashboard.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Make a user the owner/admin of an organization (fixes onboarding loop)."
    )
    parser.add_argument("--email", required=True, help="User email (auth.users)")
    parser.add_argument("--org", required=True, help="Organization name")
    parser.add_argument("--job-title", default="Administrator", help="Job title on membership row")
    parser.add_argument(
        "--admin-not-owner",
        action="store_true",
        help="Grant admin org_role without changing organizations.owner_user_id",
    )
    args = parser.parse_args()

    client = _service_client()
    promote_org_admin(
        client,
        email=args.email,
        org_name=args.org,
        job_title=args.job_title,
        make_owner=not args.admin_not_owner,
    )


if __name__ == "__main__":
    main()
