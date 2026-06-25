#!/usr/bin/env bash
# Railway API service — set Config Path to deploy/railway-api.toml (or copy start command).
set -euo pipefail
cd "$(dirname "$0")/.."
exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
