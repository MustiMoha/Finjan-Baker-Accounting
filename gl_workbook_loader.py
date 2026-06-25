"""Download master workbook from Storage and build GL activity DataFrame (shared by Dashboard / Financials)."""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional, Tuple

import pandas as pd
import streamlit as st

import database as db
import excel_engine as xleng
import supabase_storage_workbook as sbw

# ``0`` = load every logical posting from the workbook (recommended for Balance Sheet accuracy).
_GL_DF_TAIL_DEFAULT = 0
_GL_RAW_READ_TAIL_DEFAULT = 0


def load_gl_activity_dataframe(
    client: Any,
    secrets: Mapping[str, Any],
    *,
    tail: int = 0,
) -> Tuple[pd.DataFrame, Optional[str]]:
    """Returns `(df, error_message)`. Empty df if error."""
    path_secret = str(secrets.get("MASTER_WORKBOOK_STORAGE_PATH") or "").strip()
    object_path = db.resolve_master_workbook_file_id(client, path_secret)
    if not object_path.strip():
        return pd.DataFrame(), "No workbook linked. Add one in **Settings** or set **MASTER_WORKBOOK_STORAGE_PATH**."
    bucket = sbw.master_workbook_bucket(secrets)
    gl_sheet = db.resolve_gl_sheet_name(client)
    layout = db.fetch_gl_layout_json(client)
    tmp_path = None
    try:
        tmp_path = sbw.download_master_to_tempfile(client, bucket, object_path)
        ext = os.path.splitext(tmp_path)[1].lower()
        if ext not in (".xlsx", ".xlsm"):
            return pd.DataFrame(), f"This view needs an Excel workbook (.xlsx or .xlsm). Current type: `{ext}`."
        from datetime import date as _date

        ta_sheet = db.resolve_t_accounts_sheet_name(client)
        raw = xleng.read_gl_sheet_rows_from_path(
            tmp_path,
            tail=tail,
            sheet_name=gl_sheet,
            layout=layout or None,
            keep_excel_row=False,
        )
        records_for_df = raw
        if ta_sheet:
            records_for_df = xleng.enrich_gl_records_with_tac_openings(
                raw,
                tmp_path,
                gl_sheet_name=gl_sheet,
                t_accounts_sheet_name=ta_sheet,
                default_year=_date.today().year,
            )
        fy_month = db.fetch_fiscal_start_month(client)
        try:
            fx_tbl = db.fetch_fx_rates_json(client)
        except Exception:
            fx_tbl = {}
        return xleng.gl_flat_records_activity_dataframe(
            records_for_df, fy_month, table_rates_foreign_to_usd=fx_tbl
        ), None
    except Exception as e:
        return pd.DataFrame(), str(e)
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def get_session_gl_activity_dataframe(
    client: Any,
    secrets: Mapping[str, Any],
    *,
    tail: int = 0,
) -> tuple[pd.DataFrame, Optional[str]]:
    """
    Reuse the last in-session download when available so Dashboard / Financials stay aligned.

    Populated by :func:`refresh_workbook_session_cache`.
    """
    t = int(tail)
    if (
        "gl_activity_df" in st.session_state
        and int(st.session_state.get("gl_activity_df_tail") or -1) == t
    ):
        return st.session_state["gl_activity_df"], st.session_state.get("gl_activity_err")
    df, err = load_gl_activity_dataframe(client, secrets, tail=t)
    st.session_state["gl_activity_df"] = df
    st.session_state["gl_activity_err"] = err
    st.session_state["gl_activity_df_tail"] = t
    return df, err


def refresh_workbook_session_cache(
    client: Any,
    secrets: Mapping[str, Any],
    *,
    df_tail: int = _GL_DF_TAIL_DEFAULT,
    raw_read_tail: int = _GL_RAW_READ_TAIL_DEFAULT,
    faux_preserve_prior: list[dict[str, Any]] | None = None,
    faux_deleted_excel_rows: set[int] | list[int] | None = None,
) -> Optional[str]:
    """
    One Storage download: fills raw GL rows (with Excel row metadata) and the activity DataFrame.

    Returns an error string on failure (session cache may be partially empty).
    """
    path_secret = str(secrets.get("MASTER_WORKBOOK_STORAGE_PATH") or "").strip()
    object_path = db.resolve_master_workbook_file_id(client, path_secret)
    rt = int(raw_read_tail)
    dt = int(df_tail)
    # Either limit being “unlimited” (<=0) means keep every logical row for statements.
    read_tail = 0 if (rt <= 0 or dt <= 0) else max(rt, dt)

    if not object_path.strip():
        st.session_state.pop("master_gl_rows_raw", None)
        st.session_state["gl_activity_df"] = pd.DataFrame()
        st.session_state["gl_activity_err"] = "No workbook linked."
        st.session_state["gl_activity_df_tail"] = int(read_tail)
        return st.session_state["gl_activity_err"]

    bucket = sbw.master_workbook_bucket(secrets)
    gl_sheet = db.resolve_gl_sheet_name(client)
    layout = db.fetch_gl_layout_json(client)
    tmp_path = None

    try:
        tmp_path = sbw.download_master_to_tempfile(client, bucket, object_path)
        ext = os.path.splitext(tmp_path)[1].lower()
        if ext not in (".xlsx", ".xlsm"):
            err = f"This view needs an Excel workbook (.xlsx or .xlsm). Current type: `{ext}`."
            st.session_state["gl_activity_df"] = pd.DataFrame()
            st.session_state["gl_activity_err"] = err
            st.session_state["gl_activity_df_tail"] = int(read_tail)
            st.session_state.pop("master_gl_rows_raw", None)
            return err

        from datetime import date as _date

        ta_sheet = db.resolve_t_accounts_sheet_name(client)
        raw = xleng.read_gl_sheet_rows_from_path(
            tmp_path,
            tail=read_tail,
            sheet_name=gl_sheet,
            layout=layout or None,
            keep_excel_row=True,
        )
        if faux_preserve_prior and faux_deleted_excel_rows is not None:
            raw = xleng.stabilize_gl_records_after_faux_delete(
                faux_preserve_prior,
                raw,
                faux_deleted_excel_rows,
            )
        fy_month = db.fetch_fiscal_start_month(client)
        try:
            fx_tbl = db.fetch_fx_rates_json(client)
        except Exception:
            fx_tbl = {}

        import gl_editor as gled

        raw = gled.normalize_gl_records_for_display(raw)

        records_for_df = raw
        if ta_sheet:
            records_for_df = xleng.enrich_gl_records_with_tac_openings(
                raw,
                tmp_path,
                gl_sheet_name=gl_sheet,
                t_accounts_sheet_name=ta_sheet,
                default_year=_date.today().year,
                keep_excel_row=True,
            )

        df_full = xleng.gl_flat_records_activity_dataframe(
            records_for_df, fy_month, table_rates_foreign_to_usd=fx_tbl
        )

        st.session_state["master_gl_rows_raw"] = raw
        st.session_state["master_gl_read_tail"] = read_tail
        st.session_state["gl_activity_df"] = df_full
        st.session_state["gl_activity_err"] = None
        st.session_state["gl_activity_df_tail"] = int(read_tail)
        st.session_state["workbook_cache_gen"] = int(st.session_state.get("workbook_cache_gen") or 0) + 1
        st.session_state.pop("_staff_peek_tr", None)
        return None
    except Exception as e:
        msg = str(e)
        st.session_state["gl_activity_df"] = pd.DataFrame()
        st.session_state["gl_activity_err"] = msg
        st.session_state["gl_activity_df_tail"] = int(read_tail)
        st.session_state.pop("master_gl_rows_raw", None)
        return msg
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def mark_financials_navigation_and_refresh_workbook(client: Any, secrets: Mapping[str, Any]) -> None:
    """When the user navigates to Financials from another page, sync the shared workbook cache."""
    prev = str(st.session_state.get("_app_page_marker") or "")
    if prev != "financials":
        refresh_workbook_session_cache(
            client,
            secrets,
            df_tail=_GL_DF_TAIL_DEFAULT,
            raw_read_tail=_GL_RAW_READ_TAIL_DEFAULT,
        )
    st.session_state["_app_page_marker"] = "financials"


def peek_next_transaction_number(
    client: Any,
    secrets: Mapping[str, Any],
) -> tuple[Any | None, bool, Optional[str]]:
    """
    Returns ``(suggested_next, has_tr_column, error_message)``.

    ``has_tr_column`` is False when the linked workbook has no transaction-number column — not an error.
    """
    path_secret = str(secrets.get("MASTER_WORKBOOK_STORAGE_PATH") or "").strip()
    object_path = db.resolve_master_workbook_file_id(client, path_secret)
    if not object_path.strip():
        return None, False, "No workbook linked."
    bucket = sbw.master_workbook_bucket(secrets)
    gl_sheet = db.resolve_gl_sheet_name(client)
    layout = db.fetch_gl_layout_json(client)
    tmp_path = None
    try:
        tmp_path = sbw.download_master_to_tempfile(client, bucket, object_path)
        if not xleng.path_supports_gl_append(tmp_path):
            return None, False, "Link an Excel .xlsx or .xlsm workbook to read transaction numbers."
        sug, has_col, err = xleng.peek_next_transaction_number_from_workbook(
            tmp_path, sheet_name=gl_sheet, layout=layout or None
        )
        return sug, has_col, err
    except Exception as e:
        return None, False, str(e)
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
