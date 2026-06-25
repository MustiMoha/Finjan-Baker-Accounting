"""Download / upload the master workbook via Supabase Storage (authenticated user JWT)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Mapping

from supabase import Client

from workbook_files import mime_type_for_filename


def normalize_storage_object_path(path: str) -> str:
    p = (path or "").strip().replace("\\", "/").lstrip("/")
    if not p:
        raise ValueError("Storage path is empty")
    if ".." in p.split("/"):
        raise ValueError("Invalid storage path")
    return p


def master_workbook_bucket(secrets: Mapping[str, Any]) -> str:
    v = secrets.get("MASTER_WORKBOOK_BUCKET")
    name = str(v).strip() if v is not None else ""
    return name or "accounting-master"


def download_master_to_tempfile(client: Client, bucket: str, object_path: str) -> str:
    normalized = normalize_storage_object_path(object_path)
    data = client.storage.from_(bucket).download(normalized)
    suffix = Path(normalized).suffix or ".xlsx"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
    finally:
        tmp.close()
    return tmp.name


def upload_master_bytes(
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


def upload_master_file(client: Client, bucket: str, object_path: str, local_path: str) -> None:
    with open(local_path, "rb") as f:
        data = f.read()
    upload_master_bytes(client, bucket, object_path, data, filename_hint=local_path)
