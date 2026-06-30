# Ali Al Baker — Vercel + Fly.io setup

Supabase is already configured. Deploy the repo and set the variables below.

**Repo:** [https://github.com/MustiMoha/Finjan-Baker-Accounting](https://github.com/MustiMoha/Finjan-Baker-Accounting)

After deploy you will have three public URLs — fill them in everywhere marked `YOUR_VERCEL_URL`, `YOUR_API_URL`, `YOUR_STREAMLIT_URL`.

Full reference: [deploy/VERCEL_FLY.md](VERCEL_FLY.md)

---

## Prerequisites

- [Fly CLI](https://fly.io/docs/flyctl/install/) (`fly auth login`)
- Vercel project for `auth_web` (or use existing)
- Supabase migration `20260610120000_streamlit_handoff_codes.sql` applied (handoff across Fly machines)

---

## Shared credentials (copy into Fly secrets / Vercel)

| Key | Value |
|-----|--------|
| `SUPABASE_URL` | `https://cafomnrnrniqigzvbhho.supabase.co` |
| `SUPABASE_ANON_KEY` | (anon JWT from Supabase Dashboard → Settings → API) |
| `SUPABASE_SERVICE_ROLE_KEY` | Ask repo owner (API service only — never commit) |
| `MASTER_WORKBOOK_BUCKET` | `accounting-master` |
| `DOCUMENTS_BUCKET` | `accounting-documents` |

---

## 1. Fly.io — API (first app)

```bash
# From repo root — change app name in deploy/fly-api.toml if needed
fly apps create ali-al-baker-api   # skip if app exists
fly deploy --config deploy/fly-api.toml
```

Public URL → `YOUR_API_URL` (e.g. `https://ali-al-baker-api.fly.dev`). Test: `YOUR_API_URL/api/health` → `{"status":"ok"}`.

**Secrets** (repeat `-c deploy/fly-api.toml` on every `fly secrets` command):

```bash
fly secrets set -c deploy/fly-api.toml \
  SUPABASE_URL="https://cafomnrnrniqigzvbhho.supabase.co" \
  SUPABASE_ANON_KEY="YOUR_ANON_KEY" \
  SUPABASE_SERVICE_ROLE_KEY="YOUR_SERVICE_ROLE_KEY" \
  AUTH_WEB_URL="YOUR_VERCEL_URL" \
  STREAMLIT_URL="YOUR_STREAMLIT_URL" \
  SERVE_AUTH_UI="false" \
  MASTER_WORKBOOK_BUCKET="accounting-master" \
  DOCUMENTS_BUCKET="accounting-documents"
```

Set `AUTH_WEB_URL` and `STREAMLIT_URL` after Vercel and Streamlit apps exist; then redeploy or restart machines.

---

## 2. Fly.io — Streamlit (second app)

```bash
fly apps create ali-al-baker-streamlit
fly deploy --config deploy/fly-streamlit.toml
```

Public URL → `YOUR_STREAMLIT_URL` (e.g. `https://ali-al-baker-streamlit.fly.dev`).

**Secrets:**

```bash
fly secrets set -c deploy/fly-streamlit.toml \
  SUPABASE_URL="https://cafomnrnrniqigzvbhho.supabase.co" \
  SUPABASE_ANON_KEY="YOUR_ANON_KEY" \
  AUTH_WEB_URL="YOUR_API_URL" \
  STREAMLIT_URL="YOUR_STREAMLIT_URL" \
  MASTER_WORKBOOK_BUCKET="accounting-master" \
  DOCUMENTS_BUCKET="accounting-documents"
```

`AUTH_WEB_URL` must be the **Fly API URL** (Streamlit calls `/api/streamlit/exchange`), not Vercel.

---

## 3. Vercel — React app

1. Import repo; **Root Directory** = `auth_web`.
2. Framework: **Vite** (`auth_web/vercel.json`).
3. **Environment variables** (Production) — then **redeploy** (values are baked in at build time):

| Variable | Value |
|----------|--------|
| `VITE_SUPABASE_URL` | `https://cafomnrnrniqigzvbhho.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | (same anon key as above) |
| `VITE_API_URL` | `YOUR_API_URL` — Fly **API** app URL, no `/api` suffix |
| `VITE_STREAMLIT_URL` | `YOUR_STREAMLIT_URL` |

4. Public URL → `YOUR_VERCEL_URL`.

---

## 4. Wire URLs back (order matters)

1. Deploy **API** → get `YOUR_API_URL`
2. Deploy **Streamlit** → get `YOUR_STREAMLIT_URL` (set `AUTH_WEB_URL=YOUR_API_URL` on Streamlit)
3. Deploy **Vercel** with `VITE_API_URL` and `VITE_STREAMLIT_URL`
4. Set Fly API secrets: `AUTH_WEB_URL=YOUR_VERCEL_URL`, `STREAMLIT_URL=YOUR_STREAMLIT_URL`
5. Smoke test: sign in on Vercel → **Financials** opens Streamlit

---

## Financials 404?

`VITE_API_URL` must be the **API** Fly URL (`…api.fly.dev`), not Streamlit. No trailing `/api`. Redeploy Vercel after changing.

---

## Local development

```bash
python start.py
```

Uses `.streamlit/secrets.toml` (not committed). See root `.env.example`.

---

## Legacy Railway

Railway configs remain in `deploy/railway-*.toml` for reference; production target is Fly.io.
