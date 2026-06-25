"""Onboarding setup routes — role selection and workbook upload."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from supabase import Client

from api.config import streamlit_secrets_dict
from api.deps import get_active_member_client
from services.onboarding_setup import complete_org_setup, needs_org_setup

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


class SetupStatusResponse(BaseModel):
    setup_required: bool
    has_workbook: bool
    current_view_role: str | None = None


@router.get("/setup-status", response_model=SetupStatusResponse)
def setup_status(
    client: Annotated[Client, Depends(get_active_member_client)],
) -> SetupStatusResponse:
    secrets = streamlit_secrets_dict()
    required = needs_org_setup(client, secrets)
    path_secret = str(secrets.get("MASTER_WORKBOOK_STORAGE_PATH") or "").strip()
    import database as db

    try:
        wb = db.resolve_master_workbook_file_id(client, path_secret)
    except Exception:
        wb = ""
    legacy = db.fetch_user_role(client)
    view = None
    if legacy == "admin":
        view = "admin"
    elif legacy == "staff":
        view = "accountant"
    elif legacy == "auditor":
        view = "viewer"
    return SetupStatusResponse(
        setup_required=required,
        has_workbook=bool(wb and str(wb).strip()),
        current_view_role=view,
    )


class CompleteSetupBody(BaseModel):
    view_role: Literal["admin", "accountant", "viewer"]
    skip_workbook: bool = False


@router.post("/complete")
async def complete_setup(
    client: Annotated[Client, Depends(get_active_member_client)],
    view_role: Annotated[str, Form()],
    skip_workbook: Annotated[bool, Form()] = False,
    file: UploadFile | None = File(None),
) -> dict[str, Any]:
    role = view_role.strip().lower()
    if role not in ("admin", "accountant", "viewer"):
        raise HTTPException(status_code=400, detail="Choose Admin, Accountant, or Viewer.")

    payload = None
    filename = None
    if file and file.filename:
        payload = await file.read()
        filename = file.filename

    try:
        doc = complete_org_setup(
            client,
            view_role=role,  # type: ignore[arg-type]
            secrets=streamlit_secrets_dict(),
            workbook_bytes=payload,
            workbook_filename=filename,
            skip_workbook=skip_workbook,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        detail = str(exc).strip() or "Setup failed"
        raise HTTPException(status_code=500, detail=detail) from exc
    return {"status": "completed", **doc}
