#!/usr/bin/env bash
# Fly.io / Railway Streamlit (Financials) service — Fly: fly deploy --config deploy/fly-streamlit.toml
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p .streamlit

# Streamlit reads secrets.toml; on Fly/Railway inject the same keys as env vars.
write_secret() {
  local key="$1"
  local val="${2:-}"
  if [ -n "$val" ]; then
    # TOML basic strings — escape backslashes and quotes minimally
    val="${val//\\/\\\\}"
    val="${val//\"/\\\"}"
    printf '%s = "%s"\n' "$key" "$val"
  fi
}

{
  write_secret "SUPABASE_URL" "${SUPABASE_URL:-}"
  write_secret "SUPABASE_ANON_KEY" "${SUPABASE_ANON_KEY:-}"
  write_secret "AUTH_WEB_URL" "${AUTH_WEB_URL:-}"
  write_secret "STREAMLIT_URL" "${STREAMLIT_URL:-}"
  write_secret "MASTER_WORKBOOK_BUCKET" "${MASTER_WORKBOOK_BUCKET:-}"
  write_secret "DOCUMENTS_BUCKET" "${DOCUMENTS_BUCKET:-}"
  write_secret "MASTER_WORKBOOK_STORAGE_PATH" "${MASTER_WORKBOOK_STORAGE_PATH:-}"
} > .streamlit/secrets.toml

PORT="${PORT:-8501}"
exec streamlit run app.py \
  --server.headless true \
  --server.address 0.0.0.0 \
  --server.port "$PORT" \
  --browser.gatherUsageStats false
