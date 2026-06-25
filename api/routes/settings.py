"""App settings routes — fiscal calendar, FX, buckets, workbook."""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from supabase import Client

import database as db
import org
import supabase_storage_workbook as sbw
from api.config import streamlit_secrets_dict
from api.deps import get_active_member_client, request_meta
from api.permissions import require_owner_accountant_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _settings_payload(client: Client) -> dict[str, Any]:
    org.sync_org_context(client)
    secrets = streamlit_secrets_dict()
    org_id = org.get_current_org_id()
    path_secret = str(secrets.get("MASTER_WORKBOOK_STORAGE_PATH") or "").strip()
    workbook_path = db.resolve_master_workbook_file_id(client, path_secret)
    return {
        "fiscal_start_month": db.fetch_fiscal_start_month(client),
        "display_currency_iso": db.fetch_display_currency_iso(client),
        "fx_rates_json": db.fetch_fx_rates_json(client),
        "fx_rates_defaults": db.default_fx_rates_usd_per_unit(),
        "account_buckets_json": db.fetch_account_buckets_json(client),
        "gl_layout_json": db.fetch_gl_layout_json(client),
        "balance_sheet_anchor_json": db.fetch_balance_sheet_anchor_json(client),
        "workbook": {
            "storage_path": workbook_path or None,
            "gl_sheet_name": db.resolve_gl_sheet_name(client),
            "t_accounts_sheet_name": db.resolve_t_accounts_sheet_name(client),
        },
        "permissions": {
            "can_initial_upload": org.can_upload_initial_workbook(client, org_id),
            "can_replace_workbook": org.can_replace_workbook(client, org_id),
            "can_settings": True,
        },
    }


@router.get("")
def get_settings(
    client: Annotated[Client, Depends(get_active_member_client)],
) -> dict[str, Any]:
    require_owner_accountant_settings(client)
    return _settings_payload(client)


class FiscalMonthRequest(BaseModel):
    month: int = Field(ge=1, le=12)


class DisplayCurrencyRequest(BaseModel):
    iso_code: str = Field(min_length=3, max_length=3)


class FxRatesRequest(BaseModel):
    rates: dict[str, float]


class AccountBucketsRequest(BaseModel):
    doc: dict[str, Any]


class GlLayoutRequest(BaseModel):
    layout: dict[str, Any]


class SheetNamesRequest(BaseModel):
    gl_sheet_name: Optional[str] = None
    t_accounts_sheet_name: Optional[str] = None


@router.patch("/fiscal-month")
def patch_fiscal_month(
    body: FiscalMonthRequest,
    client: Annotated[Client, Depends(get_active_member_client)],
) -> dict[str, int]:
    require_owner_accountant_settings(client)
    db.update_fiscal_start_month(client, body.month)
    return {"fiscal_start_month": body.month}


@router.patch("/display-currency")
def patch_display_currency(
    body: DisplayCurrencyRequest,
    client: Annotated[Client, Depends(get_active_member_client)],
) -> dict[str, str]:
    require_owner_accountant_settings(client)
    db.update_display_currency_iso(client, body.iso_code)
    return {"display_currency_iso": body.iso_code.strip().upper()[:3]}


@router.patch("/fx-rates")
def patch_fx_rates(
    body: FxRatesRequest,
    client: Annotated[Client, Depends(get_active_member_client)],
) -> dict[str, Any]:
    require_owner_accountant_settings(client)
    db.update_fx_rates_json(client, body.rates)
    return {"fx_rates_json": body.rates}


@router.patch("/account-buckets")
def patch_account_buckets(
    body: AccountBucketsRequest,
    client: Annotated[Client, Depends(get_active_member_client)],
    meta: Annotated[tuple[str | None, str | None], Depends(request_meta)],
) -> dict[str, str]:
    require_owner_accountant_settings(client)
    org_id = org.sync_org_context(client)
    before = db.fetch_account_buckets_json(client)
    db.update_account_buckets_json(client, body.doc)
    ua, ip = meta
    try:
        actor_email = db.get_current_user_email(client)
    except Exception:
        actor_email = None
    buckets = body.doc.get("buckets") if isinstance(body.doc.get("buckets"), list) else []
    maps = body.doc.get("mappings") if isinstance(body.doc.get("mappings"), list) else []
    org.log_audit_event(
        client,
        org_id=org_id,
        action="account_buckets.updated",
        client_ip=ip,
        user_agent=ua,
        details={
            "actor_email": actor_email,
            "source": "settings",
            "bucket_count": len(buckets),
            "mapping_count": len(maps),
            "before_bucket_count": len(before.get("buckets") or [])
            if isinstance(before.get("buckets"), list)
            else 0,
            "after_bucket_count": len(buckets),
        },
    )
    return {"status": "updated"}


@router.patch("/gl-layout")
def patch_gl_layout(
    body: GlLayoutRequest,
    client: Annotated[Client, Depends(get_active_member_client)],
) -> dict[str, str]:
    require_owner_accountant_settings(client)
    try:
        db.update_gl_layout_json(client, body.layout)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "updated"}


@router.patch("/sheet-names")
def patch_sheet_names(
    body: SheetNamesRequest,
    client: Annotated[Client, Depends(get_active_member_client)],
) -> dict[str, str]:
    require_owner_accountant_settings(client)
    db.update_master_workbook_sheet_names(
        client,
        gl_sheet_name=body.gl_sheet_name,
        t_accounts_sheet_name=body.t_accounts_sheet_name,
    )
    return {"status": "updated"}


@router.post("/workbook")
async def upload_workbook(
    client: Annotated[Client, Depends(get_active_member_client)],
    meta: Annotated[tuple[str | None, str | None], Depends(request_meta)],
    file: UploadFile = File(...),
    filename: Optional[str] = None,
) -> dict[str, Any]:
    require_owner_accountant_settings(client)
    org.sync_org_context(client)
    org_id = org.get_current_org_id(client)
    secrets = streamlit_secrets_dict()
    has_existing = bool(db.fetch_master_workbook_file_id(client))
    can_initial = org.can_upload_initial_workbook(client, org_id)
    can_replace = org.can_replace_workbook(client, org_id)
    if not has_existing and not can_initial:
        raise HTTPException(status_code=403, detail="Only the owner can upload the initial workbook.")
    if has_existing and not can_replace:
        raise HTTPException(status_code=403, detail="You cannot replace the workbook.")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty file")
    hint = filename or file.filename or "accounting_master.xlsx"
    bucket = sbw.master_workbook_bucket(secrets)
    op = org.master_workbook_path_for_org(org_id, hint)
    try:
        sbw.upload_master_bytes(client, bucket, op, payload, filename_hint=hint)
        db.update_master_workbook_file_id(client, op)
        ua, ip = meta
        org.log_audit_event(
            client,
            org_id=org_id,
            action="workbook.uploaded" if not has_existing else "workbook.replaced",
            success=True,
            client_ip=ip,
            user_agent=ua,
            details={"path": op},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"storage_path": op, "status": "uploaded"}
