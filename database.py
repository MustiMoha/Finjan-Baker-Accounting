"""Supabase client helpers: auth session, CRUD for dashboard tables."""

from __future__ import annotations

import base64
import json
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from typing import Any, Mapping, Optional

from supabase import Client, create_client

import account_buckets as _account_buckets


def _org_id_for_query(client: Client | None = None) -> Optional[str]:
    try:
        import org as org_mod

        if client is not None:
            bound = org_mod.org_id_from_client(client)
            if bound:
                org_mod.set_current_org_id(bound)
                return bound
        return org_mod.try_get_current_org_id()
    except Exception:
        return None


def _require_org_id(client: Client | None = None) -> str:
    oid = _org_id_for_query(client)
    if oid:
        return oid
    raise RuntimeError("No organization context")


def _app_settings_row(client: Client, columns: str) -> Optional[dict[str, Any]]:
    oid = _org_id_for_query(client)
    if oid:
        row = client.table("app_settings").select(columns).eq("org_id", oid).limit(1).execute()
    else:
        row = client.table("app_settings").select(columns).eq("id", 1).limit(1).execute()
    if not row.data:
        return None
    return row.data[0]


def _app_settings_update(client: Client, payload: dict[str, Any]) -> None:
    oid = _org_id_for_query(client)
    if oid:
        client.table("app_settings").update(payload).eq("org_id", oid).execute()
    else:
        client.table("app_settings").update(payload).eq("id", 1).execute()


def get_supabase_client(url: str, anon_key: str) -> Client:
    return create_client(url, anon_key)


def _jwt_payload(access_token: str) -> Optional[dict[str, Any]]:
    try:
        parts = access_token.split(".")
        if len(parts) < 2:
            return None
        pad = "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _jwt_exp_unix(access_token: str) -> Optional[int]:
    payload = _jwt_payload(access_token)
    if not payload:
        return None
    exp = payload.get("exp")
    return int(exp) if exp is not None else None


def _jwt_sub(access_token: str) -> Optional[str]:
    payload = _jwt_payload(access_token)
    if not payload:
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None


def _bound_access_token(client: Client) -> Optional[str]:
    tok = getattr(client, "_baker_access_token", None)
    if tok:
        return str(tok)
    auth = client.options.headers.get("Authorization") or ""
    if isinstance(auth, str) and auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def apply_access_token(client: Client, access_token: str) -> None:
    client.options.headers["Authorization"] = f"Bearer {access_token}"
    client._baker_access_token = access_token
    client._postgrest = None
    client._storage = None


def _apply_auth_headers(client: Client, access_token: str) -> None:
    apply_access_token(client, access_token)


def bind_session_tokens(
    client: Client,
    access_token: str,
    refresh_token: str,
    *,
    refresh_skew_sec: int = 60,
    allow_refresh: bool = True,
) -> tuple[str, str]:
    """
    Attach the user JWT to PostgREST without refreshing when the access token is still valid.

    Supabase rotates refresh tokens on use. Streamlit must pass ``allow_refresh=False`` so it
    never steals the refresh token from the React app.
    """
    access_token = str(access_token or "").strip()
    refresh_token = str(refresh_token or "").strip()
    if not access_token:
        raise ValueError("Missing access token")

    exp = _jwt_exp_unix(access_token)
    now = int(time.time())
    access_usable = exp is None or exp > now

    if access_usable and (exp is None or exp > now + refresh_skew_sec):
        try:
            user = client.auth.get_user(access_token)
            if user is not None and user.user is not None:
                _apply_auth_headers(client, access_token)
                return access_token, refresh_token
        except Exception:
            if exp is not None and exp > now:
                _apply_auth_headers(client, access_token)
                return access_token, refresh_token

    if not allow_refresh:
        if access_usable:
            _apply_auth_headers(client, access_token)
            return access_token, refresh_token
        raise ValueError("Access token expired")

    if not refresh_token:
        if access_usable:
            _apply_auth_headers(client, access_token)
            return access_token, refresh_token
        raise ValueError("Missing refresh token")

    try:
        client.auth.set_session(access_token, refresh_token)
    except Exception:
        if access_usable:
            _apply_auth_headers(client, access_token)
            return access_token, refresh_token
        raise

    active_at = access_token
    active_rt = refresh_token
    try:
        sess = client.auth.get_session()
        if sess is not None:
            if sess.access_token:
                active_at = sess.access_token
            if sess.refresh_token:
                active_rt = sess.refresh_token
    except Exception:
        pass
    _apply_auth_headers(client, active_at)
    return active_at, active_rt


def access_token_usable(access_token: str, *, skew_sec: int = 0) -> bool:
    exp = _jwt_exp_unix(str(access_token or ""))
    if exp is None:
        return bool(str(access_token or "").strip())
    return exp > int(time.time()) + skew_sec


def set_session(client: Client, access_token: str, refresh_token: str) -> None:
    bind_session_tokens(client, access_token, refresh_token)


def sign_in_email(client: Client, email: str, password: str) -> dict[str, Any]:
    res = client.auth.sign_in_with_password({"email": email, "password": password})
    if res.session is None:
        raise RuntimeError("Sign-in failed")
    return {"access_token": res.session.access_token, "refresh_token": res.session.refresh_token, "user": res.user}


def sign_up_email(client: Client, email: str, password: str) -> dict[str, Any]:
    res = client.auth.sign_up({"email": email, "password": password})
    if res.session is not None:
        return {
            "access_token": res.session.access_token,
            "refresh_token": res.session.refresh_token,
            "user": res.user,
            "session_ready": True,
        }
    return {"user": res.user, "session_ready": False}


def sign_out(client: Client) -> None:
    client.auth.sign_out()


def get_current_user_id(client: Client) -> str:
    token = _bound_access_token(client)
    if token:
        try:
            u = client.auth.get_user(token)
            if u is not None and u.user is not None:
                return u.user.id
        except Exception:
            sub = _jwt_sub(token)
            if sub:
                return sub

    try:
        u = client.auth.get_user()
        if u is not None and u.user is not None:
            return u.user.id
    except Exception:
        pass
    raise RuntimeError("Not authenticated")


def fetch_user_profile(client: Client, user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    uid = user_id or get_current_user_id(client)
    try:
        row = client.table("profiles").select("id,email,full_name").eq("id", uid).limit(1).execute()
        if row.data:
            return row.data[0]
    except Exception:
        pass
    return None


def update_profile_full_name(client: Client, full_name: str) -> dict[str, Any]:
    uid = get_current_user_id(client)
    nm = (full_name or "").strip()[:120]
    client.table("profiles").update(
        {"full_name": nm or None, "updated_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", uid).execute()
    return fetch_user_profile(client, uid) or {"id": uid, "full_name": nm}


def fetch_profiles_by_ids(client: Client, user_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not user_ids:
        return {}
    try:
        prof = (
            client.table("profiles")
            .select("id,email,full_name")
            .in_("id", list({str(x) for x in user_ids if x}))
            .execute()
        )
        return {str(p["id"]): p for p in (prof.data or []) if p.get("id")}
    except Exception:
        return {}


def get_current_user_email(client: Client) -> Optional[str]:
    token = _bound_access_token(client)
    if token:
        try:
            u = client.auth.get_user(token)
            if u is not None and u.user is not None:
                em = getattr(u.user, "email", None)
                return str(em) if em else None
        except Exception:
            payload = _jwt_payload(token)
            if payload:
                em = payload.get("email")
                return str(em) if em else None

    try:
        u = client.auth.get_user()
        if u is not None and u.user is not None:
            em = getattr(u.user, "email", None)
            return str(em) if em else None
    except Exception:
        pass
    return None


def fetch_user_role(client: Client) -> Optional[str]:
    uid = get_current_user_id(client)
    row = (
        client.table("user_roles")
        .select("role")
        .eq("user_id", uid)
        .limit(1)
        .execute()
    )
    if not row.data:
        return None
    return row.data[0]["role"]


def fetch_fiscal_start_month(client: Client) -> int:
    row = _app_settings_row(client, "fiscal_year_start_month")
    if not row:
        return 1
    return int(row["fiscal_year_start_month"])


def fetch_master_workbook_file_id(client: Client) -> Optional[str]:
    row = _app_settings_row(client, "master_workbook_file_id")
    if not row:
        return None
    v = row.get("master_workbook_file_id")
    return str(v).strip() if v else None


def resolve_master_workbook_file_id(client: Client, secrets_fallback: str) -> str:
    """Prefer storage path saved in app_settings; else MASTER_WORKBOOK_STORAGE_PATH from secrets."""
    db_id = fetch_master_workbook_file_id(client)
    if db_id:
        return db_id
    return (secrets_fallback or "").strip()


def update_master_workbook_file_id(client: Client, file_id: Optional[str]) -> None:
    uid = get_current_user_id(client)
    payload: dict[str, Any] = {
        "master_workbook_file_id": (file_id or "").strip() or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": uid,
    }
    if not (file_id or "").strip():
        payload["master_workbook_gl_sheet_name"] = None
        payload["master_workbook_t_accounts_sheet_name"] = None
    _app_settings_update(client, payload)


_DEFAULT_GL_SHEET = "GL"


def fetch_master_workbook_gl_sheet_name(client: Client) -> Optional[str]:
    row = _app_settings_row(client, "master_workbook_gl_sheet_name")
    if not row:
        return None
    v = row.get("master_workbook_gl_sheet_name")
    return str(v).strip() if v else None


def fetch_master_workbook_t_accounts_sheet_name(client: Client) -> Optional[str]:
    row = _app_settings_row(client, "master_workbook_t_accounts_sheet_name")
    if not row:
        return None
    v = row.get("master_workbook_t_accounts_sheet_name")
    return str(v).strip() if v else None


def resolve_gl_sheet_name(client: Client) -> str:
    v = fetch_master_workbook_gl_sheet_name(client)
    return v if v else _DEFAULT_GL_SHEET


def resolve_t_accounts_sheet_name(client: Client) -> Optional[str]:
    return fetch_master_workbook_t_accounts_sheet_name(client)


def update_master_workbook_sheet_names(
    client: Client,
    *,
    gl_sheet_name: str,
    t_accounts_sheet_name: Optional[str],
) -> None:
    uid = get_current_user_id(client)
    g = gl_sheet_name.strip()
    ta = (t_accounts_sheet_name or "").strip() or None
    _app_settings_update(
        client,
        {
            "master_workbook_gl_sheet_name": g or None,
            "master_workbook_t_accounts_sheet_name": ta,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": uid,
        },
    )


def fetch_display_currency_iso(client: Client) -> str:
    row = _app_settings_row(client, "display_currency_iso")
    if not row:
        return "USD"
    v = row.get("display_currency_iso")
    s = str(v).strip().upper() if v else ""
    return s[:3] if len(s) >= 3 else "USD"


def update_fiscal_start_month(client: Client, month: int) -> None:
    if month < 1 or month > 12:
        raise ValueError("month must be 1–12")
    uid = get_current_user_id(client)
    _app_settings_update(
        client,
        {"fiscal_year_start_month": month, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": uid},
    )


def update_display_currency_iso(client: Client, iso_code: str) -> None:
    iso = (iso_code or "").strip().upper()[:3]
    if len(iso) != 3:
        raise ValueError("Use a 3-letter ISO 4217 currency code")
    uid = get_current_user_id(client)
    _app_settings_update(
        client,
        {
            "display_currency_iso": iso,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": uid,
        },
    )


def fetch_fx_rates_json(client: Client) -> dict[str, float]:
    row = _app_settings_row(client, "fx_rates_json")
    if not row:
        return {}
    raw = row.get("fx_rates_json")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        iso = str(k).strip().upper()[:3]
        if len(iso) != 3:
            continue
        try:
            f = float(v)
            if f > 0:
                out[iso] = f
        except (TypeError, ValueError):
            continue
    return out


def default_fx_rates_usd_per_unit() -> dict[str, float]:
    """
    Builtin spot rates: **USD per 1 unit** of each foreign ISO (same convention as ``fx_rates_json``
    and ``get_conversion_rate``’s ``table_rates_foreign_to_usd``).
    """
    return dict(_DEFAULT_FX_UNITS_OF_USD_PER_UNIT)


def update_fx_rates_json(client: Client, rates: dict[str, float]) -> None:
    clean: dict[str, float] = {}
    for k, v in (rates or {}).items():
        iso = str(k).strip().upper()[:3]
        if len(iso) != 3:
            continue
        try:
            f = float(v)
            if f <= 0:
                raise ValueError(f"Rate for {iso} must be positive")
            clean[iso] = f
        except (TypeError, ValueError) as e:
            if isinstance(e, ValueError) and "must be positive" in str(e):
                raise
            continue
    uid = get_current_user_id(client)
    _app_settings_update(
        client,
        {
            "fx_rates_json": clean,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": uid,
        },
    )


# Built-in spot rates: USD per 1 unit of foreign currency (override via app_settings.fx_rates_json / callers).
_DEFAULT_FX_UNITS_OF_USD_PER_UNIT: dict[str, float] = {
    "EUR": 1.10,
    "GBP": 1.27,
    "JPY": 0.0067,
    "CAD": 0.74,
    "AUD": 0.65,
    "INR": 0.012,
    "CHF": 1.12,
    "CNY": 0.14,
    "NZD": 0.61,
    "QAR": 0.2747,
}


def get_conversion_rate(
    source_currency: str,
    target_currency: str,
    asof_date: Optional[date] = None,
    *,
    table_rates_foreign_to_usd: Optional[dict[str, float]] = None,
) -> float:
    """
    Return **units of target currency per one unit of source** (spot approximation).

    ``table_rates_foreign_to_usd`` stores **USD per 1 unit** of each foreign ISO (see Settings exchange table —
    values are kept in this form even when reporting currency is not USD).

    ``asof_date`` is reserved for future dated FX; it does not change the result today.
    """
    _ = asof_date
    src = (source_currency or "USD").strip().upper()[:3]
    tgt = (target_currency or "USD").strip().upper()[:3]
    if len(src) != 3:
        src = "USD"
    if len(tgt) != 3:
        tgt = "USD"
    if src == tgt:
        return 1.0

    merged: dict[str, float] = dict(_DEFAULT_FX_UNITS_OF_USD_PER_UNIT)
    if table_rates_foreign_to_usd:
        for k, v in table_rates_foreign_to_usd.items():
            iso = str(k).strip().upper()[:3]
            if len(iso) != 3:
                continue
            try:
                fv = float(v)
                if fv > 0:
                    merged[iso] = fv
            except (TypeError, ValueError):
                continue

    def usd_per_unit(code: str) -> float:
        if code == "USD":
            return 1.0
        return float(merged.get(code, 1.0))

    num = usd_per_unit(src)
    den = usd_per_unit(tgt)
    if den <= 0:
        return 1.0
    return num / den


def fetch_gl_layout_json(client: Client) -> dict[str, Any]:
    """GL layout: manual/auto, column indices (0-based), optional ``header_first_row`` / ``data_start_row``."""
    try:
        row = _app_settings_row(client, "gl_layout_json")
    except Exception:
        return {}
    if not row:
        return {}
    raw = row.get("gl_layout_json")
    if raw is None or not isinstance(raw, dict):
        return {}
    return dict(raw)


def fetch_account_buckets_json(client: Client) -> dict[str, Any]:
    row = _app_settings_row(client, "account_buckets_json")
    if not row:
        return {"mappings": []}
    raw = row.get("account_buckets_json")
    if raw is None:
        return {"mappings": []}
    if not isinstance(raw, dict):
        return {"mappings": []}
    return _account_buckets.normalize_buckets_document(raw)


def update_account_buckets_json(client: Client, doc: dict[str, Any]) -> None:
    cleaned = _account_buckets.bucket_document_for_api(doc)
    uid = get_current_user_id(client)
    _app_settings_update(
        client,
        {
            "account_buckets_json": cleaned,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": uid,
        },
    )


_DEFAULT_RATIO_THRESHOLDS: dict[str, Any] = {
    "gross_margin_pct": {"min": 25},
    "operating_margin_pct": {"min": 5},
    "quick_ratio": {"min": 1.0},
}


def fetch_ratio_thresholds_json(client: Client) -> dict[str, Any]:
    try:
        row = _app_settings_row(client, "ratio_thresholds_json")
    except Exception:
        return dict(_DEFAULT_RATIO_THRESHOLDS)
    if not row:
        return dict(_DEFAULT_RATIO_THRESHOLDS)
    raw = row.get("ratio_thresholds_json")
    if not isinstance(raw, dict):
        return dict(_DEFAULT_RATIO_THRESHOLDS)
    out = dict(_DEFAULT_RATIO_THRESHOLDS)
    out.update(raw)
    return out


def update_ratio_thresholds_json(client: Client, doc: dict[str, Any]) -> None:
    merged = fetch_ratio_thresholds_json(client)
    merged.update(doc)
    uid = get_current_user_id(client)
    _app_settings_update(
        client,
        {
            "ratio_thresholds_json": merged,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": uid,
        },
    )


def fetch_onboarding_json(client: Client) -> dict[str, Any]:
    try:
        row = _app_settings_row(client, "onboarding_json")
    except Exception:
        return {}
    if not row:
        return {}
    raw = row.get("onboarding_json")
    return dict(raw) if isinstance(raw, dict) else {}


def update_onboarding_json(client: Client, doc: dict[str, Any]) -> None:
    merged = fetch_onboarding_json(client)
    merged.update(doc)
    uid = get_current_user_id(client)
    _app_settings_update(
        client,
        {
            "onboarding_json": merged,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": uid,
        },
    )


_DEFAULT_FORECAST_CONFIG: dict[str, Any] = {
    "horizon_periods": 12,
    "revenue_methods": {
        "bottom_up": {"enabled": True, "weight": 50},
        "time_series": {"enabled": True, "weight": 50},
    },
    "expense_methods": {
        "pct_of_sales": {"enabled": True, "weight": 34},
        "historical_incremental": {"enabled": True, "weight": 33},
        "scenario": {"enabled": True, "weight": 33},
    },
    "bottom_up": {
        "monthly_traffic": 10000,
        "conversion_rate_pct": 2.5,
        "average_order_value": 150,
        "sales_headcount": 3,
        "quota_per_rep": 25000,
    },
    "time_series": {"yoy_growth_pct": 5.0},
    "pct_of_sales": {"cogs_pct": 45.0, "marketing_pct": 8.0, "shipping_pct": 3.0},
    "historical_incremental": {"overhead_annual_growth_pct": 3.0},
    "scenario": {
        "best_revenue_mult": 1.15,
        "base_revenue_mult": 1.0,
        "worst_revenue_mult": 0.85,
        "best_expense_mult": 0.95,
        "base_expense_mult": 1.0,
        "worst_expense_mult": 1.12,
    },
    "custom_assumptions": [],
}


def fetch_forecast_config_json(client: Client) -> dict[str, Any]:
    try:
        row = _app_settings_row(client, "forecast_config_json")
    except Exception:
        return dict(_DEFAULT_FORECAST_CONFIG)
    if not row:
        return dict(_DEFAULT_FORECAST_CONFIG)
    raw = row.get("forecast_config_json")
    if not isinstance(raw, dict):
        return dict(_DEFAULT_FORECAST_CONFIG)
    out = dict(_DEFAULT_FORECAST_CONFIG)
    for key, val in raw.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            merged = dict(out[key])
            merged.update(val)
            out[key] = merged
        else:
            out[key] = val
    from services.financial_forecast import sanitize_forecast_config

    return sanitize_forecast_config(out)


def update_forecast_config_json(client: Client, doc: dict[str, Any]) -> None:
    from services.financial_forecast import sanitize_forecast_config

    merged = sanitize_forecast_config(fetch_forecast_config_json(client))
    doc = sanitize_forecast_config(doc)
    for key, val in doc.items():
        if isinstance(val, dict) and isinstance(merged.get(key), dict):
            sub = dict(merged[key])
            sub.update(val)
            merged[key] = sub
        else:
            merged[key] = val
    uid = get_current_user_id(client)
    _app_settings_update(
        client,
        {
            "forecast_config_json": merged,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": uid,
        },
    )


def update_gl_layout_json(client: Client, layout: dict[str, Any]) -> None:
    uid = get_current_user_id(client)
    merged = dict(layout)
    mode = str(merged.get("mode") or "auto").strip().lower()
    if mode not in ("auto", "manual"):
        raise ValueError("layout.mode must be 'auto' or 'manual'")
    try:
        hf = max(1, int(merged.get("header_first_row") or 1))
    except (TypeError, ValueError):
        hf = 1
    merged["header_first_row"] = hf
    dsr_raw = merged.get("data_start_row")
    try:
        if dsr_raw is not None:
            merged["data_start_row"] = max(hf + 1, int(dsr_raw))
    except (TypeError, ValueError):
        merged.pop("data_start_row", None)
    merged["mode"] = mode

    if mode == "manual":
        cols = merged.get("columns")
        if not isinstance(cols, dict):
            raise ValueError("manual mode requires layout.columns (object)")
        for key in ("date", "details", "particulars", "debit", "credit"):
            if key not in cols:
                raise ValueError(f"manual layout.columns missing {key!r} (0-based column index)")
            int(cols[key])
    payload = {
        "gl_layout_json": merged,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": uid,
    }
    _app_settings_update(client, payload)


def fetch_balance_sheet_anchor_json(client: Client) -> dict[str, Any]:
    """Optional workbook cell references used on Financials (e.g. Retained earnings on master file)."""
    try:
        row = _app_settings_row(client, "balance_sheet_anchor_json")
    except Exception:
        return {}
    if not row:
        return {}
    raw = row.get("balance_sheet_anchor_json")
    if raw is None or not isinstance(raw, dict):
        return {}
    return dict(raw)


def update_balance_sheet_anchor_json(client: Client, retained_earnings_sheet: Optional[str], retained_earnings_cell_a1: Optional[str]) -> None:
    """Save or clear ``retained_earnings.{sheet, cell_a1}`` in ``balance_sheet_anchor_json``."""
    uid = get_current_user_id(client)
    anchor = fetch_balance_sheet_anchor_json(client)
    sh = (retained_earnings_sheet or "").strip()
    ca_raw = (retained_earnings_cell_a1 or "").strip().upper().replace("$", "")
    if sh and ca_raw:
        anchor["retained_earnings"] = {"sheet": sh, "cell_a1": ca_raw}
    else:
        anchor.pop("retained_earnings", None)
    _app_settings_update(
        client,
        {
            "balance_sheet_anchor_json": anchor,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": uid,
        },
    )


def suggest_accounts_from_description(client: Client, description: str, limit: int = 5) -> list[dict[str, Any]]:
    """Match account_rules by keyword ilike; tie-break by priority desc."""
    if not description.strip():
        return []
    oid = _org_id_for_query(client)
    tokens = [t for t in description.lower().split() if len(t) >= 3]
    if not tokens:
        pattern = f"%{description.strip()}%"
        q = (
            client.table("account_rules")
            .select("keyword, debit_account, credit_account, priority")
            .eq("active", True)
            .ilike("keyword", pattern)
            .order("priority", desc=True)
            .limit(limit)
        )
        if oid:
            q = q.eq("org_id", oid)
        return (q.execute().data) or []

    # Or filter in Python for multiple token hits
    res_q = (
        client.table("account_rules")
        .select("keyword, debit_account, credit_account, priority")
        .eq("active", True)
        .order("priority", desc=True)
    )
    if oid:
        res_q = res_q.eq("org_id", oid)
    res = res_q.execute()
    rows = res.data or []
    desc_lower = description.lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for r in rows:
        kw = (r.get("keyword") or "").lower()
        score = 0
        if kw and kw in desc_lower:
            score += 100 + int(r.get("priority") or 0)
        for tok in tokens:
            if tok in kw:
                score += 10 + int(r.get("priority") or 0)
        if score > 0:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    return [x[1] for x in scored[:limit]]


def normalize_journal_lines_for_insert(
    lines: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """
    Validate a compound journal body for pending_transactions.journal_lines.
    Returns JSON-serializable rows: {account, debit, credit} as decimal strings (2 dp).
    """
    if len(lines) < 2:
        raise ValueError("A compound entry needs at least two lines")
    out: list[dict[str, str]] = []
    debit_sum = Decimal("0")
    credit_sum = Decimal("0")
    q = Decimal("0.01")
    for raw in lines:
        acct = str(raw.get("account") or "").strip()
        if not acct:
            raise ValueError("Each line needs an account name")
        try:
            debit = Decimal(str(raw.get("debit") or "0").replace(",", "")).quantize(q)
            credit = Decimal(str(raw.get("credit") or "0").replace(",", "")).quantize(q)
        except (InvalidOperation, ValueError) as e:
            raise ValueError("Invalid debit or credit amount on a line") from e
        if debit < 0 or credit < 0:
            raise ValueError("Amounts cannot be negative")
        dnz = debit > 0
        cnz = credit > 0
        if dnz == cnz:
            raise ValueError(f"Line «{acct}»: enter exactly one non-zero debit or credit")
        debit_sum += debit
        credit_sum += credit
        out.append({"account": acct, "debit": format(debit, "f"), "credit": format(credit, "f")})
    if debit_sum <= 0 or credit_sum <= 0:
        raise ValueError("The entry must include both debit-side and credit-side lines")
    if debit_sum.quantize(q) != credit_sum.quantize(q):
        raise ValueError(f"Total debits ({debit_sum}) must equal total credits ({credit_sum})")
    return out


def insert_pending_transaction(
    client: Client,
    *,
    description: str,
    posting_date: Optional[date] = None,
    currency_iso: str = "USD",
    amount: Optional[Decimal] = None,
    debit_account: Optional[str] = None,
    credit_account: Optional[str] = None,
    journal_lines: Optional[list[dict[str, Any]]] = None,
    invoice_extraction_json: Optional[dict[str, Any]] = None,
    gl_transaction_no: Optional[str] = None,
) -> dict[str, Any]:
    uid = get_current_user_id(client)
    oid = _org_id_for_query(client)
    iso = (currency_iso or "USD").strip().upper()[:3]
    if len(iso) != 3:
        iso = "USD"
    base: dict[str, Any] = {
        "created_by": uid,
        "description": description.strip(),
        "currency_iso": iso,
        "posting_date": (posting_date or date.today()).isoformat(),
        "status": "pending",
    }
    if oid:
        base["org_id"] = oid

    if journal_lines is not None:
        normed = normalize_journal_lines_for_insert(journal_lines)
        payload = {
            **base,
            "journal_lines": normed,
            "amount": None,
            "debit_account": None,
            "credit_account": None,
        }
    else:
        if amount is None or amount <= 0:
            raise ValueError("Amount must be positive")
        dab = (debit_account or "").strip()
        cab = (credit_account or "").strip()
        if not dab or not cab:
            raise ValueError("Debit and credit accounts are required")
        payload = {
            **base,
            "amount": str(amount),
            "debit_account": dab,
            "credit_account": cab,
            "journal_lines": None,
        }

    if invoice_extraction_json is not None:
        payload["invoice_extraction_json"] = invoice_extraction_json

    if gl_transaction_no is not None:
        gtn = str(gl_transaction_no).strip()
        if gtn:
            payload["gl_transaction_no"] = gtn

    ins = client.table("pending_transactions").insert(payload).execute()
    if not ins.data:
        raise RuntimeError("Insert failed")
    return ins.data[0]


def list_pending_transactions(client: Client, status: str = "pending") -> list[dict[str, Any]]:
    q = client.table("pending_transactions").select("*").eq("status", status)
    oid = _org_id_for_query(client)
    if oid:
        q = q.eq("org_id", oid)
    return (q.order("created_at", desc=True).execute().data) or []


def list_my_pending(client: Client) -> list[dict[str, Any]]:
    uid = get_current_user_id(client)
    q = client.table("pending_transactions").select("*").eq("created_by", uid)
    oid = _org_id_for_query(client)
    if oid:
        q = q.eq("org_id", oid)
    return (q.order("created_at", desc=True).execute().data) or []


def count_pending_transactions(client: Client, *, status: str = "pending") -> int:
    q = client.table("pending_transactions").select("id", count="exact").eq("status", status).limit(1)
    oid = _org_id_for_query(client)
    if oid:
        q = q.eq("org_id", oid)
    return int(getattr(q.execute(), "count", None) or 0)


def update_pending_status(
    client: Client,
    pending_id: str,
    *,
    status: str,
    reviewed_by: Optional[str] = None,
    drive_revision_id: Optional[str] = None,
    last_error: Optional[str] = None,
    clear_last_error: bool = False,
) -> None:
    payload: dict[str, Any] = {"status": status}
    if status in ("approved", "rejected"):
        payload["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    if reviewed_by:
        payload["reviewed_by"] = reviewed_by
    if drive_revision_id is not None:
        payload["drive_revision_id"] = drive_revision_id
    if clear_last_error:
        payload["last_error"] = None
    elif last_error is not None:
        payload["last_error"] = last_error
    client.table("pending_transactions").update(payload).eq("id", pending_id).execute()


def set_pending_error(client: Client, pending_id: str, message: str) -> None:
    client.table("pending_transactions").update({"last_error": message}).eq("id", pending_id).execute()


def update_pending_invoice_attachment(
    client: Client,
    pending_id: str,
    *,
    object_path: str,
    original_filename: str,
) -> None:
    client.table("pending_transactions").update(
        {
            "invoice_object_path": normalize_pending_invoice_path(object_path),
            "invoice_original_filename": (original_filename or "")[:512] or None,
        }
    ).eq("id", pending_id).execute()


def normalize_pending_invoice_path(path: str) -> str:
    p = (path or "").strip().replace("\\", "/").lstrip("/")
    if not p:
        raise ValueError("Invoice storage path is empty")
    if ".." in p.split("/"):
        raise ValueError("Invalid invoice storage path")
    return p


def fetch_statement_templates_json(client: Client) -> dict[str, Any]:
    row = _app_settings_row(client, "statement_templates_json")
    if not row:
        return {}
    raw = row.get("statement_templates_json")
    return raw if isinstance(raw, dict) else {}


def update_statement_template_record(
    client: Client,
    *,
    kind: str,
    object_path: str,
) -> None:
    """Merge template metadata into app_settings.statement_templates_json."""
    k = (kind or "").strip()
    if not k:
        raise ValueError("template kind is required")
    uid = get_current_user_id(client)
    doc = fetch_statement_templates_json(client)
    op = normalize_pending_invoice_path(object_path)
    doc[k] = {
        "object_path": op,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _app_settings_update(
        client,
        {"statement_templates_json": doc, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": uid},
    )


def log_sign_in_event(
    client: Client,
    *,
    email: Optional[str] = None,
    role: Optional[str] = None,
    user_agent: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> None:
    """Best-effort audit row for dashboard sign-ins (requires migration + RLS)."""
    try:
        uid = get_current_user_id(client)
    except RuntimeError:
        return
    try:
        client.table("audit_sign_ins").insert(
            {
                "user_id": uid,
                "email": (email or "")[:512] or None,
                "role": (role or "")[:32] or None,
                "user_agent": (user_agent or "")[:2000] or None,
                "client_ip": (client_ip or "")[:128] or None,
            }
        ).execute()
    except Exception:
        pass
    try:
        import org as org_mod

        org_mod.log_audit_event(
            client,
            action="auth.sign_in",
            org_id=org_mod.try_get_current_org_id(client),
            details={"email": (email or "")[:512] or None, "role": (role or "")[:32] or None},
            success=True,
            client_ip=client_ip,
            user_agent=user_agent,
        )
    except Exception:
        pass


def fetch_audit_sign_ins(client: Client, *, limit: int = 500) -> list[dict[str, Any]]:
    q = (
        client.table("audit_sign_ins")
        .select("id,user_id,email,role,occurred_at,user_agent,client_ip")
        .order("occurred_at", desc=True)
        .limit(limit)
        .execute()
    )
    return q.data or []


def list_profiles_with_roles(client: Client) -> list[dict[str, Any]]:
    prof = client.table("profiles").select("id,email,updated_at").order("email").execute()
    roles = client.table("user_roles").select("user_id,role").execute()
    rid: dict[str, str] = {str(r["user_id"]): str(r["role"]) for r in (roles.data or [])}
    rows: list[dict[str, Any]] = []
    for p in prof.data or []:
        pid = str(p["id"])
        rows.append({"id": pid, "email": p.get("email") or "", "role": rid.get(pid, ""), "updated_at": p.get("updated_at")})
    return rows


def update_user_role(client: Client, user_id: str, role: str) -> None:
    r = role.strip().lower()
    if r not in ("admin", "staff", "auditor"):
        raise ValueError("role must be admin, staff, or auditor")
    client.table("user_roles").upsert({"user_id": user_id, "role": r}).execute()


def gl_activity_row_fingerprint(row: Mapping[str, Any]) -> str:
    """
    Stable id for a single GL activity row (legacy / fallback).

    Uses date, description, account, debit/credit (original column), and currency ISO.
    """
    gd = row.get("gl_date")
    if gd is not None and hasattr(gd, "isoformat"):
        d_s = str(gd.isoformat())[:10]
    elif gd is not None:
        d_s = str(gd)[:10]
    else:
        d_s = ""
    desc = str(row.get("description") or "").strip().lower()
    acct = str(row.get("account") or "").strip()
    try:
        deb = round(float(row.get("debit") or 0), 6)
    except (TypeError, ValueError):
        deb = 0.0
    try:
        cred = round(float(row.get("credit") or 0), 6)
    except (TypeError, ValueError):
        cred = 0.0
    ccy = str(row.get("currency_iso") or "USD").strip().upper()[:3]
    if len(ccy) < 3:
        ccy = "USD"
    payload = f"{d_s}|{desc}|{acct}|{deb}|{cred}|{ccy}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def gl_transaction_fingerprint(row: Mapping[str, Any]) -> str:
    """
    Fingerprint for one **journal entry** (compound transaction): every line with the same
    ``journal_entry_seq`` shares this id so one-time tagging applies to the whole entry.

    Falls back to :func:`gl_activity_row_fingerprint` when journal metadata is missing.
    """
    seq_raw = row.get("journal_entry_seq")
    try:
        seq_i = int(seq_raw) if seq_raw is not None and str(seq_raw).strip() != "" else 0
    except (TypeError, ValueError):
        seq_i = 0
    if seq_i <= 0:
        return gl_activity_row_fingerprint(row)

    gd = row.get("gl_date")
    if gd is not None and hasattr(gd, "isoformat"):
        d_s = str(gd.isoformat())[:10]
    elif gd is not None:
        d_s = str(gd)[:10]
    else:
        d_s = ""
    desc = str(row.get("description") or "").strip().lower()
    try:
        fy = int(row.get("fiscal_year") or 0)
    except (TypeError, ValueError):
        fy = 0
    try:
        fp_n = int(row.get("fiscal_period") or 0)
    except (TypeError, ValueError):
        fp_n = 0
    payload = f"journal|{d_s}|{desc}|{fy}|{fp_n}|{seq_i}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fetch_one_time_transaction_fingerprints(client: Client) -> set[str]:
    """All fingerprints currently in the one-time bucket."""
    try:
        q = client.table("one_time_transaction_marks").select("fingerprint")
        oid = _org_id_for_query(client)
        if oid:
            q = q.eq("org_id", oid)
        rows = q.execute()
    except Exception:
        return set()
    out: set[str] = set()
    for r in rows.data or []:
        fp = r.get("fingerprint")
        if fp:
            out.add(str(fp))
    return out


def sync_one_time_transaction_marks(client: Client, fingerprints_checked: list[tuple[str, bool]]) -> None:
    """
    For each ``(fingerprint, checked)``, insert into the bucket or remove.

    Fingerprints are **journal-entry** ids from :func:`gl_transaction_fingerprint` when grouping exists.

    Only fingerprints listed here are updated; other stored marks are untouched.
    """
    uid = get_current_user_id(client)
    oid = _org_id_for_query(client)
    for fp, checked in fingerprints_checked:
        if len(fp) != 64:
            continue
        if checked:
            row: dict[str, Any] = {"fingerprint": fp, "created_by": uid}
            if oid:
                row["org_id"] = oid
            client.table("one_time_transaction_marks").upsert(
                row,
                on_conflict="fingerprint",
            ).execute()
        else:
            del_q = client.table("one_time_transaction_marks").delete().eq("fingerprint", fp)
            if oid:
                del_q = del_q.eq("org_id", oid)
            del_q.execute()
