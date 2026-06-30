"""ASGI entrypoint for Fly.io / `uvicorn main:app` default."""

from api.main import app

__all__ = ["app"]
