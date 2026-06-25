"""Admin: fiscal calendar and master workbook in Supabase Storage."""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import uuid

import pandas as pd
import streamlit as st

import currency_iso4217 as ccy
import database as db
import account_buckets as ab
import excel_engine as xleng
import gl_workbook_loader as gl_wb
import org
import supabase_storage_documents as sbd
import supabase_storage_workbook as sbw
from components.viewport_toast import render_viewport_toast_stack

_SHEET_PICK_KEY = "_wb_sheet_pick"
_SETTINGS_FEEDBACK_PREFIX = "_settings_feedback_"
_SETTINGS_TOAST_QUEUE_KEY = "_settings_toast_queue"


def _set_settings_feedback(slot: str, kind: str, message: str) -> None:
    """Persist one-shot confirmation for the next rerun (bottom toast stack)."""
    st.session_state[f"{_SETTINGS_FEEDBACK_PREFIX}{slot}"] = {
        "kind": kind,
        "message": message,
    }


def _enqueue_settings_toast(kind: str, message: str) -> None:
    msg = str(message or "").strip()
    if not msg:
        return
    queue = st.session_state.get(_SETTINGS_TOAST_QUEUE_KEY)
    if not isinstance(queue, list):
        queue = []
    queue.append({"kind": str(kind or "success"), "message": msg})
    st.session_state[_SETTINGS_TOAST_QUEUE_KEY] = queue


def _show_settings_feedback(slot: str) -> None:
    """Queue feedback for ``slot`` (rendered once at the bottom of the page)."""
    payload = st.session_state.pop(f"{_SETTINGS_FEEDBACK_PREFIX}{slot}", None)
    if not isinstance(payload, dict):
        return
    message = str(payload.get("message") or "")
    if not message:
        return
    _enqueue_settings_toast(str(payload.get("kind") or "success"), message)


def _render_settings_toast_stack() -> None:
    """Fixed bottom toast stack on the browser viewport (visible while scrolling)."""
    queue = st.session_state.pop(_SETTINGS_TOAST_QUEUE_KEY, None)
    if not isinstance(queue, list) or not queue:
        return
    render_viewport_toast_stack(queue)


def _bucket_remove_flag(val: object) -> bool:
    """True when the checkbox column means «drop this row on save»."""
    if val is True:
        return True
    try:
        if pd.isna(val):
            return False
    except TypeError:
        pass
    return bool(val)


def _bucket_editor_rows(buckets: list[dict]) -> list[dict]:
    rows_o: list[dict] = []
    for b in buckets:
        if not isinstance(b, dict):
            continue
        tmpl = str(b.get("template_key") or "").strip().lower()
        rows_o.append(
            {
                "remove_bucket": False,
                "name": str(b.get("name") or "").strip(),
                "category": str(b.get("category") or "asset").strip().lower(),
                "template_key": tmpl if tmpl in ab.BUCKET_TEMPLATES else "",
                "rollup": bool(b.get("rollup", True)),
                "heuristic": bool(b.get("heuristic", False)),
            }
        )
    return rows_o


def _bucket_rules_editor_rows(
    mappings: list[dict], buckets: list[dict]
) -> list[dict]:
    name_by_id = {str(b["id"]): str(b.get("name") or "") for b in buckets if isinstance(b, dict)}
    rows_o: list[dict] = []
    for m in mappings:
        if not isinstance(m, dict):
            continue
        bid = str(m.get("bucket_id") or "").strip()
        rows_o.append(
            {
                "remove_rule": False,
                "bucket_name": name_by_id.get(bid, ""),
                "match": str(m.get("match") or "contains").strip(),
                "text": str(m.get("text") or "").strip(),
            }
        )
    return rows_o


def _usd_per_one_unit_for_merge(iso: str, merged_usd_per_foreign: dict[str, float]) -> float:
    """How many USD one unit of ``iso`` is worth (same convention as stored ``fx_rates_json``)."""
    code = (iso or "USD").strip().upper()[:3]
    if len(code) != 3 or code == "USD":
        return 1.0
    v = merged_usd_per_foreign.get(code)
    if v is not None:
        try:
            fv = float(v)
            if fv > 0:
                return fv
        except (TypeError, ValueError):
            pass
    return float(db.get_conversion_rate(code, "USD", table_rates_foreign_to_usd=merged_usd_per_foreign))


def _gl_layout_stable_sig(doc: dict) -> str:
    """Hash persisted ``gl_layout_json`` so widgets can mirror what is stored in Supabase."""
    try:
        return hashlib.sha256(
            json.dumps(doc or {}, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
    except Exception:
        return ""


def _load_gl_header_options_from_storage(
    client,
    secrets: dict,
    effective_path: str,
    gl_sheet: str,
    *,
    header_first_row: int,
    data_start_row: int,
) -> list[tuple[int, str]]:
    path = str(effective_path or "").strip()
    if not path:
        return []
    bucket = sbw.master_workbook_bucket(secrets)
    try:
        raw = client.storage.from_(bucket).download(sbw.normalize_storage_object_path(path))
    except Exception:
        return []
    fn = Path(path).name
    ds_i = max(int(header_first_row) + 1, int(data_start_row))
    hf_i = max(1, min(int(header_first_row), ds_i - 1))
    return xleng.gl_header_column_options_from_bytes(
        raw,
        fn,
        gl_sheet.strip() or xleng.GL_SHEET_NAME_DEFAULT,
        header_first_row=hf_i,
        data_start_row=ds_i,
    )


def _hdr_pick_index(options: list[tuple[int, str]], saved_0based: int) -> int:
    for i, (col_ix, _) in enumerate(options):
        if col_ix == saved_0based:
            return i
    return 0


def _optional_hdr_options(options: list[tuple[int, str]]) -> list[tuple[int, str]]:
    return [(-1, "— Not used —")] + list(options)


def _optional_hdr_pick_index(with_skip: list[tuple[int, str]], saved: object) -> int:
    if saved is None or str(saved).strip() == "":
        return 0
    try:
        s = int(saved)
    except (TypeError, ValueError):
        return 0
    if s < 0:
        return 0
    for i, (col_ix, _) in enumerate(with_skip):
        if col_ix == s:
            return i
    return 0


def _default_gl_sheet_name(names: list[str]) -> str:
    for n in names:
        if n.strip().upper() == "GL":
            return n
    return names[0]


def _default_t_accounts_sheet_name(names: list[str], gl_sheet: str) -> str:
    for n in names:
        if n == gl_sheet:
            continue
        ln = n.lower().replace("_", "-")
        if "t-account" in ln or "t account" in ln or ln in ("t-accounts", "taccounts"):
            return n
    for n in names:
        if n != gl_sheet:
            return n
    return gl_sheet


def render(client) -> None:
    st.session_state["_app_page_marker"] = "settings"
    org_id = org.get_current_org_id()
    is_adminish = org.is_org_admin(client, org_id)
    can_initial_upload = org.can_upload_initial_workbook(client, org_id)
    can_replace_wb = org.can_replace_workbook(client, org_id)

    st.header("Configuration")

    if is_adminish:
        _render_admin_settings(client)
    elif can_replace_wb:
        st.caption("You can replace the master workbook below. Other settings require an owner or admin.")

    _render_workbook_settings(client, org_id, can_initial_upload, can_replace_wb, is_adminish)
    _render_settings_toast_stack()


def _render_admin_settings(client) -> None:
    st.subheader("Fiscal year")
    cur = db.fetch_fiscal_start_month(client)
    st.write("Fiscal year starts in month:")
    months = [
        (1, "January"),
        (2, "February"),
        (3, "March"),
        (4, "April"),
        (5, "May"),
        (6, "June"),
        (7, "July"),
        (8, "August"),
        (9, "September"),
        (10, "October"),
        (11, "November"),
        (12, "December"),
    ]
    labels = {m[0]: m[1] for m in months}
    choice = st.selectbox(
        "Start month",
        options=[x[0] for x in months],
        format_func=lambda i: labels[i],
        index=max(0, cur - 1),
        key="fiscal_month_select",
    )
    if st.button("Save fiscal calendar", type="primary", key="save_fiscal"):
        try:
            db.update_fiscal_start_month(client, choice)
            _set_settings_feedback("fiscal", "success", "Saved.")
        except Exception as e:
            _set_settings_feedback("fiscal", "error", str(e))
    _show_settings_feedback("fiscal")

    st.divider()
    st.subheader("Who can view shared links")
    base = ""
    try:
        base = str(st.secrets.get("PUBLIC_APP_URL") or "").strip().rstrip("/")
    except Exception:
        base = ""
    qs = "?view=viewer"
    viewer_url = f"{base}{qs}" if base else qs
    st.caption(
        "People must **sign in**. Give them the **User** role unless they need more access. "
        "This link only limits what screens appear — their permissions stay the same."
    )
    st.code(viewer_url, language="text")
    if not base:
        st.info(
            "Add **`PUBLIC_APP_URL`** to `.streamlit/secrets.toml` with your live app address so this becomes a full link."
        )

    st.divider()
    st.subheader("Main reporting currency")
    cur_ccy = db.fetch_display_currency_iso(client)
    st.write("Pick the **three-letter code** used as the default on charts and labels.")
    ccy_choice = st.selectbox(
        "Reporting currency",
        options=list(ccy.ACTIVE_ISO4217),
        index=ccy.display_currency_index(cur_ccy),
        key="settings_display_currency_select",
        help="How dollar signs and symbols show on screen. Row-by-row currency from Excel still appears until you convert amounts on the dashboard.",
    )
    if st.button("Save display currency", key="save_display_currency"):
        try:
            db.update_display_currency_iso(client, ccy_choice)
            _set_settings_feedback("display_currency", "success", "Saved.")
            st.rerun()
        except Exception as e:
            _set_settings_feedback("display_currency", "error", str(e))
    _show_settings_feedback("display_currency")

    st.divider()
    st.subheader("Exchange rates")
    report_iso = str(ccy_choice).strip().upper()[:3]
    if len(report_iso) != 3:
        report_iso = "USD"
    st.caption(
        f"Rates convert **into** your reporting currency (**{report_iso}**). "
        "For each **other** currency, enter how many reporting-currency units equal **one** unit of that currency "
        f"(example: reporting **USD**, euros **1.10** → €100 → $110). "
        "Rows below combine **built‑in USD spot rates** with saved overrides (stored internally as USD per unit). "
        "When reporting currency is **not USD**, a **USD** row shows reporting-units-per-$1 (not saved on its own)."
    )
    try:
        rates_existing = db.fetch_fx_rates_json(client)
    except Exception:
        rates_existing = {}
    defaults_usd = db.default_fx_rates_usd_per_unit()
    merged_usd = {**defaults_usd, **rates_existing}
    candidates = sorted(set(merged_usd.keys()) | ({"USD"} if report_iso != "USD" else set()))
    init_rows: list[dict[str, object]] = []
    for iso in candidates:
        if iso == report_iso:
            continue
        try:
            r = db.get_conversion_rate(iso, report_iso, table_rates_foreign_to_usd=merged_usd)
        except Exception:
            r = 1.0
        init_rows.append({"ISO": iso, "rate": float(r)})
    if not init_rows:
        init_rows = [{"ISO": "", "rate": 1.0}]
    fx_df = pd.DataFrame(init_rows)
    edited_fx = st.data_editor(
        fx_df,
        num_rows="dynamic",
        width="stretch",
        key="fx_rates_editor",
        column_config={
            "ISO": st.column_config.TextColumn("Currency code", max_chars=3, help="Three letters; skip reporting currency"),
            "rate": st.column_config.NumberColumn(
                f"Reporting units per 1 unit ({report_iso})",
                min_value=0.0000001,
                format="%.6f",
            ),
        },
    )
    if st.button("Save exchange rates", key="save_fx_rates"):
        report_iso_save = str(ccy_choice).strip().upper()[:3]
        if len(report_iso_save) != 3:
            report_iso_save = "USD"
        try:
            rates_existing_save = db.fetch_fx_rates_json(client)
        except Exception:
            rates_existing_save = {}
        defaults_usd_save = db.default_fx_rates_usd_per_unit()
        merged_for_save = {**defaults_usd_save, **rates_existing_save}
        usd_per_report = _usd_per_one_unit_for_merge(report_iso_save, merged_for_save)

        new_rates_usd: dict[str, float] = {}
        for _, row in edited_fx.iterrows():
            iso = str(row.get("ISO") or "").strip().upper()[:3]
            if len(iso) != 3:
                continue
            if iso == report_iso_save:
                continue
            if iso == "USD":
                continue
            try:
                rate_rep_per_unit = float(row.get("rate"))
                if rate_rep_per_unit <= 0:
                    continue
            except (TypeError, ValueError):
                continue
            new_rates_usd[iso] = rate_rep_per_unit * usd_per_report

        try:
            db.update_fx_rates_json(client, new_rates_usd)
            _set_settings_feedback("fx_rates", "success", "Rates saved.")
            st.rerun()
        except Exception as e:
            _set_settings_feedback("fx_rates", "error", str(e))
    _show_settings_feedback("fx_rates")

    st.divider()
    st.subheader("Account buckets")
    role = db.fetch_user_role(client)
    is_admin = role == "admin"
    if not is_admin:
        st.info("Only **administrators** can create or edit buckets. You can view the current setup below.")
    st.caption(
        "Create **named buckets** with a financial **category** (where they appear on the dashboard). "
        "Add **match rules** to attach ledger account names to a bucket. "
        "Optional **template** + **Auto-match ledger** reuse built-in name patterns (A/P, cash, salaries, etc.). "
        "Rules use longer «contains» patterns before shorter ones."
    )
    try:
        bucket_doc = db.fetch_account_buckets_json(client)
    except Exception:
        bucket_doc = ab.default_buckets_document()
    init_buckets = list(bucket_doc.get("buckets") or [])
    init_maps = list(bucket_doc.get("mappings") or [])

    bucket_rows = _bucket_editor_rows(init_buckets)
    if not bucket_rows and is_admin:
        bucket_rows = [
            {
                "remove_bucket": False,
                "name": "New bucket",
                "category": "asset",
                "template_key": "",
                "rollup": True,
                "heuristic": False,
            }
        ]
    buckets_df = pd.DataFrame(bucket_rows) if bucket_rows else pd.DataFrame(
        columns=["remove_bucket", "name", "category", "template_key", "rollup", "heuristic"]
    )
    cat_opts = sorted(ab.ALLOWED_CATEGORIES)
    tmpl_opts = [""] + sorted(ab.BUCKET_TEMPLATES)
    edited_bucket_defs = st.data_editor(
        buckets_df,
        num_rows="dynamic" if is_admin else "fixed",
        width="stretch",
        key="account_bucket_defs_editor",
        disabled=not is_admin,
        column_config={
            "remove_bucket": st.column_config.CheckboxColumn("Remove", default=False),
            "name": st.column_config.TextColumn("Bucket name", required=True, width="large"),
            "category": st.column_config.SelectboxColumn(
                "Category",
                options=cat_opts,
                help="Asset / Liability / Expense / Revenue / Equity — drives dashboard classification.",
                required=True,
            ),
            "template_key": st.column_config.SelectboxColumn(
                "Template",
                options=tmpl_opts,
                help="Optional built-in pattern (A/P, cash, …). Leave blank for rules-only buckets.",
            ),
            "rollup": st.column_config.CheckboxColumn(
                "Roll up",
                default=True,
                help="One trial-balance / T-account for all accounts in this bucket.",
            ),
            "heuristic": st.column_config.CheckboxColumn(
                "Auto-match ledger",
                default=False,
                help="When a template is set, also match ledger names automatically.",
            ),
        },
    )

    st.markdown("##### Match rules")
    rule_rows = _bucket_rules_editor_rows(init_maps, init_buckets)
    if not rule_rows and is_admin and init_buckets:
        rule_rows = [
            {
                "remove_rule": False,
                "bucket_name": str(init_buckets[0].get("name") or ""),
                "match": "contains",
                "text": "",
            }
        ]
    rules_df = pd.DataFrame(rule_rows) if rule_rows else pd.DataFrame(
        columns=["remove_rule", "bucket_name", "match", "text"]
    )
    bucket_name_opts = [str(b.get("name") or "") for b in init_buckets if str(b.get("name") or "").strip()]
    edited_rules = st.data_editor(
        rules_df,
        num_rows="dynamic" if is_admin else "fixed",
        width="stretch",
        key="account_bucket_rules_editor",
        disabled=not is_admin,
        column_config={
            "remove_rule": st.column_config.CheckboxColumn("Remove", default=False),
            "bucket_name": st.column_config.SelectboxColumn(
                "Bucket",
                options=bucket_name_opts or [""],
                required=True,
            ),
            "match": st.column_config.SelectboxColumn("Match", options=["contains", "equals"], required=True),
            "text": st.column_config.TextColumn("Account text", width="large", required=True),
        },
    )

    if is_admin:
        bs1, bs2 = st.columns(2)
        with bs1:
            save_buckets = st.button("Save account buckets", key="save_account_buckets")
        with bs2:
            request_clear_buckets = st.button(
                "Reset to defaults", type="secondary", key="request_clear_buckets"
            )
        _show_settings_feedback("buckets_save")
        _show_settings_feedback("buckets_reset")

        if request_clear_buckets:
            st.session_state["_account_buckets_clear_confirm"] = True

        if st.session_state.get("_account_buckets_clear_confirm"):
            st.warning("Replace all buckets and rules with the built-in default set?")
            c_yes, c_no = st.columns(2)
            with c_yes:
                if st.button("Confirm reset", type="primary", key="confirm_clear_buckets_yes"):
                    try:
                        db.update_account_buckets_json(client, ab.default_buckets_document())
                        st.session_state["_account_buckets_clear_confirm"] = False
                        _set_settings_feedback("buckets_reset", "success", "Buckets reset.")
                        st.rerun()
                    except Exception as e:
                        _set_settings_feedback("buckets_reset", "error", str(e))
            with c_no:
                if st.button("Cancel reset", key="confirm_clear_buckets_no"):
                    st.session_state["_account_buckets_clear_confirm"] = False
                    st.rerun()

        if save_buckets:
            buckets_by_fold: dict[str, dict[str, object]] = {}
            for _, row in edited_bucket_defs.iterrows():
                if _bucket_remove_flag(row.get("remove_bucket")):
                    continue
                bname = str(row.get("name") or "").strip()
                if not bname:
                    continue
                fk = ab.fold_bucket_key(bname)
                cat = str(row.get("category") or "asset").strip().lower()
                if cat not in ab.ALLOWED_CATEGORIES:
                    cat = "asset"
                tmpl = str(row.get("template_key") or "").strip().lower()
                if tmpl and tmpl not in ab.BUCKET_TEMPLATES:
                    tmpl = ""
                if fk in buckets_by_fold:
                    prev = buckets_by_fold[fk]
                    prev_name = str(prev.get("name") or "")
                    prev["name"] = bname if len(bname) > len(prev_name) else prev_name
                    prev["heuristic"] = bool(prev.get("heuristic")) or bool(row.get("heuristic", False))
                    prev["rollup"] = bool(prev.get("rollup", True)) or bool(row.get("rollup", True))
                    if not str(prev.get("template_key") or "") and tmpl:
                        prev["template_key"] = tmpl
                    continue
                buckets_by_fold[fk] = {
                    "id": str(uuid.uuid4()),
                    "name": bname,
                    "category": cat,
                    "template_key": tmpl,
                    "rollup": bool(row.get("rollup", True)),
                    "heuristic": bool(row.get("heuristic", False)),
                }
            built_buckets = list(buckets_by_fold.values())
            name_to_id = {fk: str(b["id"]) for fk, b in buckets_by_fold.items()}
            built_maps: list[dict[str, str]] = []
            for _, row in edited_rules.iterrows():
                if _bucket_remove_flag(row.get("remove_rule")):
                    continue
                txt = str(row.get("text") or "").strip()
                bname = str(row.get("bucket_name") or "").strip()
                if not txt or not bname:
                    continue
                bid = name_to_id.get(ab.fold_bucket_key(bname))
                if not bid:
                    continue
                match_t = str(row.get("match") or "contains").strip().lower()
                if match_t not in ("contains", "equals"):
                    match_t = "contains"
                built_maps.append({"bucket_id": bid, "text": txt, "match": match_t})
            try:
                db.update_account_buckets_json(
                    client, {"buckets": built_buckets, "mappings": built_maps}
                )
                _set_settings_feedback("buckets_save", "success", "Saved.")
                st.session_state["_account_buckets_clear_confirm"] = False
                st.rerun()
            except Exception as e:
                _set_settings_feedback("buckets_save", "error", str(e))
    else:
        save_buckets = False

    st.divider()
    st.subheader("How columns line up in Excel")
    st.caption(
        "Tell the app which spreadsheet column holds **date**, **details**, **account**, **debit**, **credit**, and so on. "
        "Set **first data row**, then **first header row**. Column headings are inferred only from Excel rows "
        "*between those bounds* (inclusive of the header row span, excluding the first data row). "
        "**Merged month banners** (e.g. a full-width «July» row right under headings) are skipped automatically when importing and during auto column detection. "
        "**Auto** scans that band for labels and guesses debit/credit; **Manual** uses the picks below."
    )
    try:
        cur_layout = db.fetch_gl_layout_json(client)
    except Exception:
        cur_layout = {}
    if not isinstance(cur_layout, dict):
        cur_layout = {}

    doc_sig = _gl_layout_stable_sig(cur_layout)
    if st.session_state.get("_persisted_gl_layout_sig") != doc_sig:
        st.session_state["_persisted_gl_layout_sig"] = doc_sig
        d_saved = max(1, int(cur_layout.get("data_start_row") or 2))
        try:
            h_saved = max(1, int(cur_layout.get("header_first_row") or 1))
        except (TypeError, ValueError):
            h_saved = 1
        if h_saved >= d_saved:
            h_saved = max(1, d_saved - 1)
        mode_v = str(cur_layout.get("mode") or "auto").strip().lower()
        if mode_v not in ("auto", "manual"):
            mode_v = "auto"
        st.session_state["gl_layout_mode_radio"] = mode_v
        st.session_state["gl_layout_header_first"] = h_saved
        st.session_state["gl_layout_data_start"] = max(d_saved, h_saved + 1)

    cols_in = cur_layout.get("columns") if isinstance(cur_layout.get("columns"), dict) else {}

    def _col_i(key: str, default: int) -> int:
        v = cols_in.get(key, default)
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    mode_gl = st.radio(
        "Layout mode",
        options=["auto", "manual"],
        format_func=lambda x: "Auto-detect columns" if x == "auto" else "Pick columns by hand",
        horizontal=True,
        key="gl_layout_mode_radio",
    )
    gl_data_start = st.number_input(
        "First data row (Excel row number — first journal line)",
        min_value=1,
        max_value=500,
        help="Amounts scan from this Excel row onward. Rows above belong to headings only.",
        key="gl_layout_data_start",
    )
    ds_eff = max(1, int(gl_data_start))
    hf_ceiling = max(1, ds_eff - 1) if ds_eff > 1 else 1
    gl_header_first = st.number_input(
        "First header row (column titles span from here through the row above first data)",
        min_value=1,
        max_value=hf_ceiling,
        key="gl_layout_header_first",
    )
    manual_gl = mode_gl == "manual"

    stored_cfg = db.fetch_master_workbook_file_id(client)
    path_secret_cfg = str(st.secrets.get("MASTER_WORKBOOK_STORAGE_PATH") or "").strip()
    effective_cfg = db.resolve_master_workbook_file_id(client, path_secret_cfg)
    gl_sheet_cfg = db.resolve_gl_sheet_name(client)

    hdr_sig = (
        effective_cfg,
        gl_sheet_cfg.strip(),
        int(gl_header_first),
        ds_eff,
    )
    rh1, rh2 = st.columns([3, 1])
    with rh1:
        if not str(effective_cfg or "").strip():
            st.warning("Link a workbook below before columns can be loaded.")
        else:
            st.caption(f"Reading sheet **{gl_sheet_cfg!r}**, file **{effective_cfg!r}**.")
    with rh2:
        if st.button("Reload headings", key="gl_reload_hdr", help="Download the file again and refresh column names"):
            st.session_state.pop("_gl_col_hdr_sig", None)
            st.rerun()

    if st.session_state.get("_gl_col_hdr_sig") != hdr_sig:
        loaded = _load_gl_header_options_from_storage(
            client,
            dict(st.secrets),
            str(effective_cfg),
            gl_sheet_cfg,
            header_first_row=int(gl_header_first),
            data_start_row=ds_eff,
        )
        st.session_state["gl_col_hdr_opts"] = loaded if loaded else xleng.fallback_gl_header_options()
        st.session_state["_gl_col_hdr_sig"] = hdr_sig

    hdr_opts: list[tuple[int, str]] = st.session_state.get("gl_col_hdr_opts") or xleng.fallback_gl_header_options()

    cur_c_def = cols_in.get("currency")
    try:
        cur_c_int = int(cur_c_def) if cur_c_def is not None and str(cur_c_def).strip() != "" else -1
    except (TypeError, ValueError):
        cur_c_int = -1
    try:
        tr_raw = cols_in.get("tr_number")
        ix_tr_saved = int(tr_raw) if tr_raw is not None and str(tr_raw).strip() != "" else -1
    except (TypeError, ValueError):
        ix_tr_saved = -1

    opt_cur = _optional_hdr_options(hdr_opts)
    opt_tr = _optional_hdr_options(hdr_opts)

    if manual_gl:
        g1, g2, g3 = st.columns(3)
        with g1:
            i_date = st.selectbox(
                "Date",
                options=range(len(hdr_opts)),
                index=_hdr_pick_index(hdr_opts, _col_i("date", 0)),
                format_func=lambda i: hdr_opts[i][1],
                key="gl_pick_date",
            )
            i_details = st.selectbox(
                "Details / narrative",
                options=range(len(hdr_opts)),
                index=_hdr_pick_index(hdr_opts, _col_i("details", 1)),
                format_func=lambda i: hdr_opts[i][1],
                key="gl_pick_details",
            )
        with g2:
            i_part = st.selectbox(
                "Particulars / account",
                options=range(len(hdr_opts)),
                index=_hdr_pick_index(hdr_opts, _col_i("particulars", 2)),
                format_func=lambda i: hdr_opts[i][1],
                key="gl_pick_part",
            )
            i_deb = st.selectbox(
                "Debit",
                options=range(len(hdr_opts)),
                index=_hdr_pick_index(hdr_opts, _col_i("debit", 3)),
                format_func=lambda i: hdr_opts[i][1],
                key="gl_pick_deb",
            )
        with g3:
            i_cred = st.selectbox(
                "Credit",
                options=range(len(hdr_opts)),
                index=_hdr_pick_index(hdr_opts, _col_i("credit", 4)),
                format_func=lambda i: hdr_opts[i][1],
                key="gl_pick_cred",
            )
            i_cur = st.selectbox(
                "Currency (optional)",
                options=range(len(opt_cur)),
                index=_optional_hdr_pick_index(opt_cur, cur_c_int),
                format_func=lambda i: opt_cur[i][1],
                key="gl_pick_cur",
            )
    else:
        i_date = i_details = i_part = i_deb = i_cred = i_cur = 0

    i_tr = st.selectbox(
        "Transaction number (optional — helps read awkward layouts)",
        options=range(len(opt_tr)),
        index=_optional_hdr_pick_index(opt_tr, ix_tr_saved),
        format_func=lambda i: opt_tr[i][1],
        key="gl_pick_tr",
        help="Leave blank on continued rows; amounts may sit beside Debit/Credit on following rows.",
    )

    if st.button("Save column layout", key="save_gl_layout_btn"):
        hf_pi = max(1, int(gl_header_first))
        ds_pi = max(hf_pi + 1, int(gl_data_start))
        layout_payload: dict = {"mode": mode_gl, "header_first_row": hf_pi, "data_start_row": ds_pi, "columns": {}}
        tr_pick = int(opt_tr[i_tr][0])
        if manual_gl:
            layout_payload["columns"] = {
                "date": int(hdr_opts[i_date][0]),
                "details": int(hdr_opts[i_details][0]),
                "particulars": int(hdr_opts[i_part][0]),
                "debit": int(hdr_opts[i_deb][0]),
                "credit": int(hdr_opts[i_cred][0]),
            }
            cur_pick = int(opt_cur[i_cur][0])
            if cur_pick >= 0:
                layout_payload["columns"]["currency"] = cur_pick
        if tr_pick >= 0:
            layout_payload.setdefault("columns", {})["tr_number"] = tr_pick
        try:
            db.update_gl_layout_json(client, layout_payload)
            _set_settings_feedback("gl_layout", "success", "Column layout saved.")
            st.rerun()
        except Exception as e:
            _set_settings_feedback("gl_layout", "error", str(e))
    _show_settings_feedback("gl_layout")


def _render_workbook_settings(
    client,
    org_id: str,
    can_initial_upload: bool,
    can_replace_wb: bool,
    is_adminish: bool,
) -> None:
    st.divider()
    st.subheader("Main workbook file")

    stored = db.fetch_master_workbook_file_id(client)
    path_secret = str(st.secrets.get("MASTER_WORKBOOK_STORAGE_PATH") or "").strip()
    effective = db.resolve_master_workbook_file_id(client, path_secret)
    bucket = sbw.master_workbook_bucket(st.secrets)

    sheet_pick: list[str] | None = st.session_state.get(_SHEET_PICK_KEY)

    if sheet_pick:
        st.warning("Pick which tab is the **general ledger** and which is **T-accounts**, then click **Save worksheet mapping**.")
        dg = _default_gl_sheet_name(sheet_pick)
        dt = _default_t_accounts_sheet_name(sheet_pick, dg)
        ix_gl = sheet_pick.index(dg) if dg in sheet_pick else 0
        ix_ta = sheet_pick.index(dt) if dt in sheet_pick else min(1, len(sheet_pick) - 1)

        pc1, pc2 = st.columns(2)
        with pc1:
            gl_sel = st.selectbox(
                "Tab — **general ledger** (approved rows go here)",
                options=sheet_pick,
                index=min(ix_gl, len(sheet_pick) - 1),
                key="pick_gl_sheet_after_upload",
            )
        with pc2:
            ta_sel = st.selectbox(
                "Tab — **T-accounts**",
                options=sheet_pick,
                index=min(ix_ta, len(sheet_pick) - 1),
                key="pick_t_accounts_after_upload",
            )
        sm1, sm2 = st.columns(2)
        with sm1:
            if st.button("Save worksheet mapping", type="primary", key="save_sheet_pick"):
                db.update_master_workbook_sheet_names(
                    client, gl_sheet_name=gl_sel, t_accounts_sheet_name=ta_sel
                )
                st.session_state.pop(_SHEET_PICK_KEY, None)
                _set_settings_feedback("sheet_pick", "success", "Tab roles saved.")
                st.rerun()
        with sm2:
            if st.button("Cancel (keep old tabs)", key="discard_sheet_pick"):
                st.session_state.pop(_SHEET_PICK_KEY, None)
                st.rerun()
        _show_settings_feedback("sheet_pick")
        st.divider()

    st.caption(
        "Excel (.xlsx or .xlsm), older Excel (.xls), or CSV works for viewing on Financials. "
        "Approvals only adds rows to .xlsx / .xlsm files using the tabs you choose."
    )

    gl_db = db.fetch_master_workbook_gl_sheet_name(client)
    ta_db = db.fetch_master_workbook_t_accounts_sheet_name(client)
    ta_display = ta_db if ta_db else "(not set)"
    st.caption(
        "Tabs now — **General ledger:** "
        f"{db.resolve_gl_sheet_name(client)!r}; **T-accounts:** {ta_display!r}."
    )

    st.caption(f"Online folder name: `{bucket}` (admins can change **MASTER_WORKBOOK_BUCKET**).")

    if stored:
        st.caption("Saved file location is stored with your app settings.")
    elif path_secret:
        st.caption("File path comes from **`MASTER_WORKBOOK_STORAGE_PATH`** in secrets — not overridden here.")
    else:
        st.warning("No workbook linked yet. Upload below or set **MASTER_WORKBOOK_STORAGE_PATH** in secrets.")

    if not can_initial_upload and not can_replace_wb:
        st.info("Workbook upload and replace are restricted to the owner (initial) and owner/admin/accountant (replace).")
        return

    org_default_path = org.master_workbook_path_for_org(org_id)

    if effective:
        st.code(effective, language="text")

    if not can_replace_wb:
        st.caption("Only the owner can perform the **first** workbook upload.")
    elif not can_initial_upload:
        st.caption("You can **replace** the linked workbook; initial upload is owner-only.")

    upl = st.file_uploader(
        "Choose a workbook",
        type=["xlsm", "xlsx", "xls", "csv"],
        key="master_workbook_uploader",
    )
    stem = Path(upl.name).stem if upl else "accounting_master"
    ext = Path(upl.name).suffix if upl else ".xlsx"
    default_nm = upl.name.strip() if upl else f"{stem}{ext}"
    fname = st.text_input(
        "File name for upload",
        value=default_nm,
        key="master_storage_filename_hint",
    )

    replace_ok = bool(effective.strip())
    mode_ix = st.radio(
        "How to upload",
        options=["new", "replace"],
        index=0,
        horizontal=True,
        format_func=lambda m: ("Save as a new path" if m == "new" else "Replace the current file"),
        key="master_upload_how",
    )

    path_default = str(stored or path_secret or org_default_path).strip()
    object_path_typed = st.text_input(
        "Path inside the folder (no leading slash)",
        value=effective if mode_ix == "replace" else path_default,
        disabled=(mode_ix == "replace"),
        key=f"master_storage_path_{mode_ix}",
    )

    if mode_ix == "replace" and not replace_ok:
        st.warning("Link or upload a workbook first — there is nothing to replace.")

    disabled = upl is None or (mode_ix == "replace" and not replace_ok) or not str(object_path_typed).strip()
    if st.button("Upload file", type="primary", disabled=disabled, key="master_upload_btn"):
        if not upl:
            _set_settings_feedback("workbook_upload", "warning", "Choose a file first.")
        else:
            has_existing = bool(effective.strip())
            blocked = False
            if mode_ix == "replace":
                if not can_replace_wb:
                    _set_settings_feedback(
                        "workbook_upload",
                        "error",
                        "You do not have permission to replace the workbook.",
                    )
                    blocked = True
            elif not has_existing:
                if not can_initial_upload:
                    _set_settings_feedback(
                        "workbook_upload",
                        "error",
                        "Only the organization owner can upload the initial workbook.",
                    )
                    blocked = True
            elif not is_adminish:
                _set_settings_feedback(
                    "workbook_upload",
                    "error",
                    "Saving to a new path requires an owner or admin.",
                )
                blocked = True
            if not blocked:
                try:
                    st.session_state.pop(_SHEET_PICK_KEY, None)
                    payload = upl.getvalue()
                    hint = fname.strip() if fname.strip() else default_nm
                    if not Path(hint).suffix:
                        hint = f"{hint}{ext or '.xlsx'}"
                    if mode_ix == "replace":
                        sbw.upload_master_bytes(
                            client,
                            bucket,
                            effective,
                            payload,
                            filename_hint=hint,
                        )
                        org.log_audit_event(
                            client,
                            action="workbook.replaced",
                            org_id=org_id,
                            details={"path": effective, "filename": hint},
                        )
                        names = xleng.list_sheet_names_from_bytes(upl.name, payload)
                        if names:
                            st.session_state[_SHEET_PICK_KEY] = names
                            _set_settings_feedback(
                                "workbook_upload",
                                "success",
                                "Uploaded. Choose GL and T-account tabs below.",
                            )
                        else:
                            _set_settings_feedback("workbook_upload", "success", "Uploaded.")
                    else:
                        op = sbw.normalize_storage_object_path(str(object_path_typed))
                        sbw.upload_master_bytes(client, bucket, op, payload, filename_hint=hint)
                        db.update_master_workbook_file_id(client, op)
                        org.log_audit_event(
                            client,
                            action="workbook.uploaded" if not has_existing else "workbook.linked",
                            org_id=org_id,
                            details={"path": op, "filename": hint},
                        )
                        names = xleng.list_sheet_names_from_bytes(upl.name, payload)
                        if names:
                            st.session_state[_SHEET_PICK_KEY] = names
                            _set_settings_feedback(
                                "workbook_upload",
                                "success",
                                "Uploaded and linked. Choose GL and T-account tabs below.",
                            )
                        else:
                            _set_settings_feedback(
                                "workbook_upload",
                                "success",
                                "Uploaded and linked. For CSV, enter tab names below if needed.",
                            )
                    gl_wb.refresh_workbook_session_cache(client, dict(st.secrets))
                    st.rerun()
                except Exception as e:
                    _set_settings_feedback("workbook_upload", "error", str(e))
    _show_settings_feedback("workbook_upload")

    st.markdown("###### Tab names (type by hand)")
    st.caption(
        "Change tab names without uploading again. After uploading Excel you may be asked which tab is which."
    )

    wg1, wg2, wg3 = st.columns([2, 2, 1])
    with wg1:
        manual_gl = st.text_input(
            "General ledger tab name",
            value=gl_db if gl_db is not None else xleng.GL_SHEET_NAME_DEFAULT,
            key="manual_gl_sheet",
        )
    with wg2:
        manual_ta = st.text_input(
            "T-accounts tab name",
            value=ta_db if ta_db is not None else "",
            key="manual_ta_sheet",
            placeholder="e.g. T-Accounts",
        )
    with wg3:
        st.write("")
        st.write("")
        if st.button("Save names", key="save_manual_sheet_names"):
            try:
                db.update_master_workbook_sheet_names(
                    client,
                    gl_sheet_name=manual_gl,
                    t_accounts_sheet_name=(manual_ta.strip() or None),
                )
                _set_settings_feedback("manual_sheet_names", "success", "Saved.")
                st.rerun()
            except Exception as e:
                _set_settings_feedback("manual_sheet_names", "error", str(e))
        _show_settings_feedback("manual_sheet_names")

    st.markdown("###### Balance sheet — retained earnings cell")
    st.caption(
        "Optional: point at the retained earnings figure on your **master workbook** so Financials can show it "
        "on the balance sheet and verify it ties to GL accounts containing both «retained» and «earnings» "
        "(e.g. «Retained earnings»). Clearing both fields removes the workbook cross-check."
    )
    anch = db.fetch_balance_sheet_anchor_json(client)
    rb = anch.get("retained_earnings") if isinstance(anch, dict) else None
    rs_default = ""
    rc_default = ""
    if isinstance(rb, dict):
        rs_default = str(rb.get("sheet") or "")
        rc_default = str(rb.get("cell_a1") or "")
    rsa, rca = st.columns(2)
    with rsa:
        bs_re_sheet = st.text_input("Worksheet name", value=rs_default, key="bs_anchor_re_sheet")
    with rca:
        bs_re_cell = st.text_input(
            "Cell (A1 notation, e.g. B12)",
            value=rc_default,
            key="bs_anchor_re_cell",
            placeholder="e.g. C24",
        )
    if st.button("Save retained earnings anchor", key="save_bs_anchor_re"):
        try:
            db.update_balance_sheet_anchor_json(client, bs_re_sheet, bs_re_cell)
            gl_wb.refresh_workbook_session_cache(client, dict(st.secrets))
            _set_settings_feedback(
                "bs_anchor_re",
                "success",
                "Saved. Financials reads this cell using formula results cached in Excel (Save in Excel after changing formulas).",
            )
            st.rerun()
        except Exception as e:
            _set_settings_feedback("bs_anchor_re", "error", str(e))
    _show_settings_feedback("bs_anchor_re")

    if stored:
        if st.button("Forget linked workbook path", key="master_clear_id"):
            st.session_state.pop(_SHEET_PICK_KEY, None)
            db.update_master_workbook_file_id(client, None)
            st.rerun()

    if not is_adminish:
        return

    st.divider()
    st.subheader("Statement templates")
    st.caption(
        "Excel layouts used on **Financials → Download statements**. Put a named range **DATA_BODY** on any sheet "
        "pointing at the **first data row**, left column — we fill four columns: account, debits, credits, net. "
        "Optional single-cell names **PARAM_AS_OF** (trial balance) and **PARAM_PERIOD_LABEL** (income summary)."
    )
    tmpl_kind = st.selectbox(
        "Template kind",
        ["trial_balance", "income_summary"],
        key="stmt_tpl_kind_select",
        format_func=lambda k: "Trial balance" if k == "trial_balance" else "Income & spending summary",
    )
    tmpl_upl = st.file_uploader("Template workbook (.xlsx / .xlsm)", type=["xlsx", "xlsm"], key="stmt_tpl_upload")
    if st.button("Save statement template", type="primary", key="stmt_tpl_save_btn"):
        if tmpl_upl is None:
            _set_settings_feedback("stmt_template", "warning", "Choose a template file first.")
        else:
            try:
                bucket = sbd.documents_bucket(st.secrets)
                fn = sbd.safe_document_filename(tmpl_upl.name)
                path = f"templates/statements/{tmpl_kind}_{fn}"
                payload = tmpl_upl.getvalue()
                sbd.upload_document_bytes(client, bucket, path, payload, filename_hint=fn)
                db.update_statement_template_record(client, kind=tmpl_kind, object_path=path)
                _set_settings_feedback("stmt_template", "success", "Saved template path to app settings.")
                st.rerun()
            except Exception as e:
                _set_settings_feedback("stmt_template", "error", str(e))
    _show_settings_feedback("stmt_template")

    try:
        doc_tmpl = db.fetch_statement_templates_json(client)
        if doc_tmpl:
            st.markdown("**Stored templates**")
            st.json(doc_tmpl)
    except Exception:
        pass
