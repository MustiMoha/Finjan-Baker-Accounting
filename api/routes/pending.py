"""Pending transaction routes — entries, approvals, invoice extract."""

from __future__ import annotations

import base64
import json
from datetime import date
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from supabase import Client

import database as db
import invoice_extract as invx
import supabase_storage_documents as sbd
from api.config import get_setting, streamlit_secrets_dict
import org
from api.deps import get_active_member_client, request_meta
from api.permissions import require_approvals, require_entries
from services.pending_approve import approve_pending_transaction

router = APIRouter(prefix="/api/pending", tags=["pending"])


def _enrich_row(
    client: Client,
    row: dict[str, Any],
    secrets: dict[str, Any],
    *,
    profiles_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    out = dict(row)
    uid = str(row.get("created_by") or "")
    if uid and profiles_by_id is not None:
        prof = profiles_by_id.get(uid) or {}
        out["submitter_email"] = prof.get("email")
        out["submitter_name"] = prof.get("full_name")
    inv_path = row.get("invoice_object_path")
    if inv_path:
        try:
            bucket = sbd.documents_bucket(secrets)
            out["invoice_url"] = sbd.create_document_signed_url(
                client, bucket, str(inv_path), expires_in=2700
            )
        except Exception:
            out["invoice_url"] = None
    jl = row.get("journal_lines")
    if isinstance(jl, str):
        try:
            out["journal_lines"] = json.loads(jl)
        except json.JSONDecodeError:
            pass
    return out


class JournalLine(BaseModel):
    account: str = ""
    debit: str = "0"
    credit: str = "0"


class CreatePendingRequest(BaseModel):
    description: str = Field(min_length=1, max_length=2000)
    posting_date: Optional[str] = None
    currency_iso: str = "USD"
    journal_lines: list[JournalLine] = Field(min_length=2)
    gl_transaction_no: Optional[str] = None
    invoice_extraction_json: Optional[dict[str, Any]] = None
    invoice_base64: Optional[str] = None
    invoice_filename: Optional[str] = None


def _enrich_rows(client: Client, rows: list[dict[str, Any]], secrets: dict[str, Any]) -> list[dict[str, Any]]:
    uids = [str(r.get("created_by")) for r in rows if r.get("created_by")]
    profiles = db.fetch_profiles_by_ids(client, uids)
    return [_enrich_row(client, r, secrets, profiles_by_id=profiles) for r in rows]


@router.get("/mine")
def list_my_pending(
    client: Annotated[Client, Depends(get_active_member_client)],
) -> list[dict[str, Any]]:
    require_entries(client)
    secrets = streamlit_secrets_dict()
    rows = db.list_my_pending(client)
    return _enrich_rows(client, rows, secrets)


@router.get("/queue")
def list_pending_queue(
    client: Annotated[Client, Depends(get_active_member_client)],
) -> list[dict[str, Any]]:
    require_approvals(client)
    secrets = streamlit_secrets_dict()
    rows = db.list_pending_transactions(client, status="pending")
    return _enrich_rows(client, rows, secrets)


@router.post("")
def create_pending(
    body: CreatePendingRequest,
    client: Annotated[Client, Depends(get_active_member_client)],
    meta: Annotated[tuple[str | None, str | None], Depends(request_meta)],
) -> dict[str, Any]:
    require_entries(client)
    posting = date.today()
    if body.posting_date:
        try:
            posting = date.fromisoformat(body.posting_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid posting_date") from exc

    lines = [ln.model_dump() for ln in body.journal_lines]
    tr_kw: dict[str, Any] = {}
    if body.gl_transaction_no and body.gl_transaction_no.strip():
        tr_kw["gl_transaction_no"] = body.gl_transaction_no.strip()

    try:
        row = db.insert_pending_transaction(
            client,
            description=body.description.strip(),
            posting_date=posting,
            currency_iso=body.currency_iso,
            journal_lines=lines,
            invoice_extraction_json=body.invoice_extraction_json,
            **tr_kw,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        detail = str(exc).strip() or "Could not submit entry"
        raise HTTPException(status_code=500, detail=detail) from exc

    if body.invoice_base64 and body.invoice_filename:
        try:
            inv_bytes = base64.b64decode(body.invoice_base64)
            bucket = sbd.documents_bucket(streamlit_secrets_dict())
            safe_nm = sbd.safe_document_filename(body.invoice_filename)
            object_path = f"invoices/{row['id']}/{safe_nm}"
            sbd.upload_document_bytes(
                client,
                bucket,
                object_path,
                inv_bytes,
                filename_hint=safe_nm,
            )
            db.update_pending_invoice_attachment(
                client,
                row["id"],
                object_path=object_path,
                original_filename=body.invoice_filename,
            )
            row["invoice_object_path"] = object_path
            row["invoice_original_filename"] = body.invoice_filename
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Entry saved but invoice upload failed: {exc}") from exc

    ua, ip = meta
    try:
        email = db.get_current_user_email(client)
    except Exception:
        email = None
    try:
        uid = db.get_current_user_id(client)
    except Exception:
        uid = None
    org.log_audit_event(
        client,
        action="entry.submitted",
        details={
            "pending_id": row.get("id"),
            "description": body.description.strip()[:200],
            "currency_iso": body.currency_iso,
            "submitter_email": email,
            "submitter_user_id": uid,
        },
        client_ip=ip,
        user_agent=ua,
    )
    return row


@router.post("/{pending_id}/reject")
def reject_pending(
    pending_id: str,
    client: Annotated[Client, Depends(get_active_member_client)],
    meta: Annotated[tuple[str | None, str | None], Depends(request_meta)],
) -> dict[str, str]:
    require_approvals(client)
    uid = db.get_current_user_id(client)
    rows = db.list_pending_transactions(client, status="pending")
    row = next((r for r in rows if str(r.get("id")) == pending_id), None)
    try:
        db.update_pending_status(client, pending_id, status="rejected", reviewed_by=uid, clear_last_error=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    ua, ip = meta
    try:
        email = db.get_current_user_email(client)
    except Exception:
        email = None
    org.log_audit_event(
        client,
        action="entry.rejected",
        details={
            "pending_id": pending_id,
            "description": (row or {}).get("description", "")[:200] if row else "",
            "reviewer_email": email,
            "reviewer_user_id": uid,
        },
        client_ip=ip,
        user_agent=ua,
    )
    return {"status": "rejected"}


@router.post("/{pending_id}/approve")
def approve_pending(
    pending_id: str,
    client: Annotated[Client, Depends(get_active_member_client)],
) -> dict[str, str]:
    require_approvals(client)
    rows = db.list_pending_transactions(client, status="pending")
    row = next((r for r in rows if str(r.get("id")) == pending_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Pending entry not found")
    try:
        approve_pending_transaction(client, row, secrets=streamlit_secrets_dict())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        detail = str(exc).strip() or "Approval failed"
        raise HTTPException(status_code=500, detail=detail) from exc
    return {"status": "approved"}


@router.post("/extract-invoice")
async def extract_invoice_file(
    client: Annotated[Client, Depends(get_active_member_client)],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    require_entries(client)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    filename = file.filename or "invoice.pdf"
    try:
        tess = get_setting("TESSERACT_CMD") or None
        invx.configure_tesseract_cmd(tess)
        ext = invx.extract_invoice(raw, filename)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    draft_lines = invx.draft_journal_lines_from_extraction(ext)
    draft_lines = invx.apply_account_rule_hints(client, draft_lines, ext)
    posting = invx.posting_date_from_extraction(ext)
    description = invx.build_description_from_extraction(ext)
    currency = ext.get("currency_guess")
    usable = invx.extraction_has_usable_amounts(ext)

    return {
        "extraction": ext,
        "draft": {
            "description": description,
            "posting_date": posting.isoformat() if posting else None,
            "currency_iso": str(currency).strip().upper()[:3] if currency else None,
            "journal_lines": draft_lines,
            "usable_amounts": usable,
        },
        "invoice_base64": base64.b64encode(raw).decode("ascii"),
        "invoice_filename": filename,
    }
