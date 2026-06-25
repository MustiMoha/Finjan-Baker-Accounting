"""
Per-browser Streamlit session isolation for workbook editing.

Each user's edits live under a namespaced key so concurrent Streamlit users do not share
in-memory row state. The on-disk file is only rewritten on explicit Save.
"""

from __future__ import annotations

import hashlib
from typing import Any

import streamlit as st


def _session_namespace() -> str:
    """Stable id for this browser tab's Streamlit session."""
    sid = getattr(st.runtime.scriptrunner, "get_script_run_ctx", lambda: None)()
    if sid is not None:
        ctx = sid()
        if ctx is not None and getattr(ctx, "session_id", None):
            return str(ctx.session_id)
    # Fallback when runtime context is unavailable (e.g. unit tests).
    return hashlib.sha256(repr(sorted(st.session_state.keys())).encode()).hexdigest()[:16]


def workbook_state_key(*, workbook_id: str, sheet: str, scope: str = "") -> str:
    """
    Build a session_state key for one workbook + sheet + optional filter scope.

    ``workbook_id`` should be the storage object id or file hash after load.
    """
    ns = _session_namespace()
    parts = f"{ns}|{workbook_id}|{sheet}|{scope}"
    digest = hashlib.sha256(parts.encode()).hexdigest()[:20]
    return f"wb_edit_{digest}"


def get_row_edits(key: str) -> list[dict[str, Any]]:
    raw = st.session_state.get(key)
    return list(raw) if isinstance(raw, list) else []


def set_row_edits(key: str, rows: list[dict[str, Any]]) -> None:
    st.session_state[key] = list(rows)


def get_pending_deletes(key: str) -> set[int]:
    raw = st.session_state.get(f"{key}_del")
    if not isinstance(raw, (list, set, tuple)):
        return set()
    return {int(x) for x in raw if int(x) > 0}


def set_pending_deletes(key: str, rows: set[int]) -> None:
    st.session_state[f"{key}_del"] = sorted(rows)


def clear_workbook_edit_state(key: str) -> None:
    st.session_state.pop(key, None)
    st.session_state.pop(f"{key}_del", None)
