"""ASGI entrypoint for Railway / Nixpacks default `uvicorn main:app`."""

from api.main import app

__all__ = ["app"]
