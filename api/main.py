"""Baker auth & onboarding API (FastAPI)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import Client

import database as db
import org
from api.config import auth_web_url, cors_allowed_origins, serve_auth_ui, streamlit_secrets_dict, streamlit_url, supabase_anon_key, supabase_url
from api.deps import get_authenticated_client, request_meta
from services.onboarding_setup import needs_org_setup
from api.routes.accountant import router as accountant_router
from api.routes.audit import router as audit_router
from api.routes.context import router as context_router
from api.routes.dashboard import router as dashboard_router
from api.routes.members import router as members_router
from api.routes.onboarding import router as onboarding_router
from api.routes.org_settings import router as org_settings_router
from api.routes.profile import router as profile_router
from api.routes.pending import router as pending_router
from api.routes.settings import router as settings_router
from api.routes.streamlit import router as streamlit_router
from api.routes.translation import router as translation_router

app = FastAPI(title="Baker API", version="0.3.0")

app.include_router(streamlit_router)
app.include_router(context_router)
app.include_router(dashboard_router)
app.include_router(pending_router)
app.include_router(members_router)
app.include_router(org_settings_router)
app.include_router(onboarding_router)
app.include_router(accountant_router)
app.include_router(audit_router)
app.include_router(settings_router)
app.include_router(profile_router)
app.include_router(translation_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", include_in_schema=False)
def health_check() -> dict[str, str]:
    return {"status": "ok"}


class ConfigResponse(BaseModel):
    streamlit_url: str
    auth_web_url: str
    supabase_url: str
    supabase_anon_key: str


class GateResponse(BaseModel):
    gate: Literal["none", "pending", "rejected", "active"]
    email: str | None = None
    org_name: str | None = None
    setup_required: bool = False


class CreateOrgRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    job_title: str = Field(min_length=1, max_length=120)


class JoinOrgRequest(BaseModel):
    join_code: str = Field(min_length=6, max_length=6)
    job_title: str = Field(min_length=1, max_length=120)


@app.get("/api/config", response_model=ConfigResponse)
def public_config() -> ConfigResponse:
    return ConfigResponse(
        streamlit_url=streamlit_url(),
        auth_web_url=auth_web_url(),
        supabase_url=supabase_url(),
        supabase_anon_key=supabase_anon_key(),
    )


@app.get("/api/membership/gate", response_model=GateResponse)
def membership_gate(
    client: Annotated[Client, Depends(get_authenticated_client)],
) -> GateResponse:
    try:
        gate = org.resolve_membership_gate(client)
    except Exception as exc:
        detail = str(exc).strip() or "Membership lookup failed"
        raise HTTPException(status_code=500, detail=detail) from exc

    try:
        email = db.get_current_user_email(client)
    except Exception:
        email = None

    org_name = None
    if gate in ("pending", "rejected"):
        try:
            mem = org.fetch_membership_any_status(client)
            if mem and mem.get("organizations"):
                org_row = mem["organizations"]
                if isinstance(org_row, dict):
                    org_name = org_row.get("name")
        except Exception:
            pass

    setup_required = False
    if gate == "active":
        try:
            setup_required = needs_org_setup(client, streamlit_secrets_dict())
        except Exception:
            setup_required = False
        oid = org.try_get_current_org_id()
        if oid:
            org.bind_org_to_client(client, oid)
    return GateResponse(gate=gate, email=email, org_name=org_name, setup_required=setup_required)


@app.post("/api/orgs/create")
def create_org(
    body: CreateOrgRequest,
    client: Annotated[Client, Depends(get_authenticated_client)],
    meta: Annotated[tuple[str | None, str | None], Depends(request_meta)],
) -> dict:
    ua, ip = meta
    try:
        row = org.create_organization(
            client,
            name=body.name,
            job_title=body.job_title,
            client_ip=ip,
            user_agent=ua,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        detail = str(exc).strip()
        if not detail:
            detail = "Could not create organization"
        raise HTTPException(status_code=500, detail=detail) from exc
    return row


@app.post("/api/orgs/join")
def join_org(
    body: JoinOrgRequest,
    client: Annotated[Client, Depends(get_authenticated_client)],
    meta: Annotated[tuple[str | None, str | None], Depends(request_meta)],
) -> dict:
    ua, ip = meta
    try:
        row = org.request_join_organization(
            client,
            join_code=body.join_code,
            job_title=body.job_title,
            client_ip=ip,
            user_agent=ua,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not submit join request") from exc
    return row


# Unknown /api/* methods should 404 — not 405 from the SPA GET catch-all below.
@app.api_route("/api/{rest:path}", methods=["POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
async def api_unmatched_write(rest: str) -> None:
    raise HTTPException(status_code=404, detail="Not found")


# Auth UI (built React app) — registered after /api routes
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_DIST = Path(__file__).resolve().parent.parent / "auth_web" / "dist"
_ASSETS = _DIST / "assets"

if serve_auth_ui() and _ASSETS.is_dir():
    app.mount("/assets", StaticFiles(directory=_ASSETS), name="auth-assets")

    @app.get("/", include_in_schema=False)
    async def auth_home() -> FileResponse:
        return FileResponse(_DIST / "index.html")

    @app.get("/{page_path:path}", include_in_schema=False)
    async def auth_spa(page_path: str) -> FileResponse:
        if page_path.startswith("api"):
            raise HTTPException(status_code=404, detail="Not found")
        file_path = _DIST / page_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_DIST / "index.html")
