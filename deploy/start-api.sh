#!/usr/bin/env bash
# Fly.io / Railway API service — Fly: fly deploy --config deploy/fly-api.toml
set -euo pipefail
cd "$(dirname "$0")/.."
exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
