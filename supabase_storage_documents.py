"""Upload / signed URLs for accounting-documents bucket (invoices, statement templates)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from supabase import Client

from workbook_files import mime_type_for_filename

from supabase_storage_workbook import normalize_storage_object_path


def documents_bucket(secrets: Mapping[str, Any]) -> str:
    v = secrets.get("DOCUMENTS_BUCKET")
    name = str(v).strip() if v is not None else ""
    return name or "accounting-documents"


def safe_document_filename(name: str) -> str:
    base = Path(name).name
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", base).strip("._") or "document"
    return cleaned[:180]


def upload_document_bytes(
    client: Client,
    bucket: str,
    object_path: str,
    data: bytes,
    *,
    filename_hint: str,
) -> None:
    normalized = normalize_storage_object_path(object_path)
    mime = mime_type_for_filename(filename_hint or normalized)
    client.storage.from_(bucket).upload(
        normalized,
        data,
        file_options={"content-type": mime, "upsert": "true"},
    )


def download_document_bytes(client: Client, bucket: str, object_path: str) -> bytes:
    normalized = normalize_storage_object_path(object_path)
    return client.storage.from_(bucket).download(normalized)


def create_document_signed_url(client: Client, bucket: str, object_path: str, *, expires_in: int = 3600) -> str:
    normalized = normalize_storage_object_path(object_path)
    res = client.storage.from_(bucket).create_signed_url(normalized, expires_in)
    if isinstance(res, dict):
        url = res.get("signedURL") or res.get("signedUrl") or res.get("signed_url")
        if url:
            return str(url)
    raise RuntimeError("Could not create signed URL for document")
