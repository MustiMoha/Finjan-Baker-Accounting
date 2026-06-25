"""Accountant home — ratios, thresholds, warnings."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
import pandas as pd
from supabase import Client

import database as db
import org
from api.config import streamlit_secrets_dict
import account_buckets as ab
from api.deps import get_active_member_client, request_meta
from api.permissions import require_lead_accountant
from services.accountant import build_accountant_home_payload
from services.financial_forecast import build_financial_forecast
from services.roles import resolve_view_role

router = APIRouter(prefix="/api/accountant", tags=["accountant"])


def _require_accountant(client: Client) -> None:
    org_id = org.sync_org_context(client)
    mem = org.fetch_active_membership(client, org_id)
    legacy = db.fetch_user_role(client)
    org_role = str((mem or {}).get("org_role") or "")
    role = resolve_view_role(legacy_role=legacy, org_role=org_role)
    if role != "accountant":
        raise HTTPException(status_code=403, detail="Accountant access required.")


@router.get("/home")
def accountant_home(
    client: Annotated[Client, Depends(get_active_member_client)],
    currency_view: Annotated[str, Query(description="original or usd")] = "original",
) -> dict[str, Any]:
    _require_accountant(client)
    try:
        return build_accountant_home_payload(
            client, streamlit_secrets_dict(), currency_view=currency_view
        )
    except Exception as exc:
        detail = str(exc).strip() or "Could not load accountant home"
        raise HTTPException(status_code=500, detail=detail) from exc


class ThresholdPatch(BaseModel):
    thresholds: dict[str, Any]


@router.get("/thresholds")
def get_thresholds(
    client: Annotated[Client, Depends(get_active_member_client)],
) -> dict[str, Any]:
    _require_accountant(client)
    return db.fetch_ratio_thresholds_json(client)


@router.patch("/thresholds")
def patch_thresholds(
    body: ThresholdPatch,
    client: Annotated[Client, Depends(get_active_member_client)],
    meta: Annotated[tuple[str | None, str | None], Depends(request_meta)],
) -> dict[str, Any]:
    _require_accountant(client)
    org_id = org.sync_org_context(client)
    before = db.fetch_ratio_thresholds_json(client)
    db.update_ratio_thresholds_json(client, body.thresholds)
    after = db.fetch_ratio_thresholds_json(client)
    ua, ip = meta
    org.log_audit_event(
        client,
        org_id=org_id,
        action="ratio_thresholds.updated",
        success=True,
        client_ip=ip,
        user_agent=ua,
        details={"before": before, "after": after},
    )
    return after


class AccountBucketsPatch(BaseModel):
    doc: dict[str, Any]


@router.get("/account-buckets")
def get_account_buckets(
    client: Annotated[Client, Depends(get_active_member_client)],
) -> dict[str, Any]:
    require_lead_accountant(client)
    return db.fetch_account_buckets_json(client)


@router.patch("/account-buckets")
def patch_account_buckets(
    body: AccountBucketsPatch,
    client: Annotated[Client, Depends(get_active_member_client)],
    meta: Annotated[tuple[str | None, str | None], Depends(request_meta)],
) -> dict[str, str]:
    require_lead_accountant(client)
    org_id = org.sync_org_context(client)
    before = db.fetch_account_buckets_json(client)
    try:
        db.update_account_buckets_json(client, body.doc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    after = ab.bucket_document_for_api(body.doc)
    ua, ip = meta
    try:
        actor_email = db.get_current_user_email(client)
    except Exception:
        actor_email = None
    buckets = after.get("buckets") if isinstance(after.get("buckets"), list) else []
    maps = after.get("mappings") if isinstance(after.get("mappings"), list) else []
    org.log_audit_event(
        client,
        org_id=org_id,
        action="account_buckets.updated",
        client_ip=ip,
        user_agent=ua,
        details={
            "actor_email": actor_email,
            "bucket_count": len(buckets),
            "mapping_count": len(maps),
            "categories": sorted(
                {str(b.get("category") or "") for b in buckets if isinstance(b, dict)}
            ),
            "before_bucket_count": len(before.get("buckets") or [])
            if isinstance(before.get("buckets"), list)
            else 0,
            "after_bucket_count": len(buckets),
        },
    )
    return {"status": "updated"}


class ForecastConfigPatch(BaseModel):
    config: dict[str, Any]


@router.get("/forecast-config")
def get_forecast_config(
    client: Annotated[Client, Depends(get_active_member_client)],
) -> dict[str, Any]:
    require_lead_accountant(client)
    return db.fetch_forecast_config_json(client)


@router.get("/forecast-preview")
def forecast_preview(
    client: Annotated[Client, Depends(get_active_member_client)],
    currency_view: Annotated[str, Query(description="original or usd")] = "original",
) -> dict[str, Any]:
    require_lead_accountant(client)
    import financial_kpis as fkpi
    import gl_workbook_loader as gl_wb

    fy = int(db.fetch_fiscal_start_month(client))
    cfg = db.fetch_forecast_config_json(client)
    df, err = gl_wb.load_gl_activity_dataframe(client, streamlit_secrets_dict(), tail=0)
    if err or df is None or df.empty:
        return build_financial_forecast(config=cfg, pl_df=pd.DataFrame(), fy_start_month=fy)
    use_usd = currency_view.strip().lower() in ("usd", "reporting", "usd_reporting")
    debit_col, credit_col = ("debit_usd", "credit_usd") if use_usd else ("debit", "credit")
    try:
        bucket_doc = db.fetch_account_buckets_json(client)
    except Exception:
        import account_buckets as ab

        bucket_doc = ab.default_buckets_document()
    pl_df = fkpi.pl_net_by_period(
        df,
        fy_start_month=fy,
        debit_col=debit_col,
        credit_col=credit_col,
        bucket_doc=bucket_doc,
    )
    pref = "$" if use_usd else ""
    return build_financial_forecast(
        config=cfg,
        pl_df=pl_df,
        fy_start_month=fy,
        currency_prefix=pref,
    )


@router.patch("/forecast-config")
def patch_forecast_config(
    body: ForecastConfigPatch,
    client: Annotated[Client, Depends(get_active_member_client)],
    meta: Annotated[tuple[str | None, str | None], Depends(request_meta)],
) -> dict[str, Any]:
    require_lead_accountant(client)
    org_id = org.sync_org_context(client)
    before = db.fetch_forecast_config_json(client)
    db.update_forecast_config_json(client, body.config)
    after = db.fetch_forecast_config_json(client)
    ua, ip = meta
    org.log_audit_event(
        client,
        org_id=org_id,
        action="forecast_config.updated",
        success=True,
        client_ip=ip,
        user_agent=ua,
        details={"before_keys": list(before.keys()), "after_keys": list(after.keys())},
    )
    return after
