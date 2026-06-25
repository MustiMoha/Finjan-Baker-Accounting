#!/usr/bin/env python3
"""Run the Baker auth API (FastAPI + uvicorn)."""

from __future__ import annotations

import uvicorn

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
