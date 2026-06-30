# Vercel (auth_web) + Fly.io (API + Streamlit) + Supabase

## Architecture

| Component | Host | Deploy |
|-----------|------|--------|
| React app | **Vercel** | Root: `auth_web` |
| FastAPI API | **Fly.io** | `fly deploy --config deploy/fly-api.toml` |
| Streamlit Financials | **Fly.io** (2nd app) | `fly deploy --config deploy/fly-streamlit.toml` |
| Database / auth / storage | **Supabase** | — |

Apply migration `20260610120000_streamlit_handoff_codes.sql` so API handoff works across multiple Fly machines.

Quick handoff for Mustafa: [deploy/DEV_SETUP.md](DEV_SETUP.md)

## Fly.io API app

1. Install [flyctl](https://fly.io/docs/flyctl/install/) and `fly auth login`.
2. Create app (once): `fly apps create ali-al-baker-api` — or edit `app` in `deploy/fly-api.toml`.
3. Deploy: `fly deploy --config deploy/fly-api.toml`
4. Set secrets: `fly secrets set -c deploy/fly-api.toml KEY=value ...` (see DEV_SETUP.md).

| Variable | Notes |
|----------|--------|
| `SUPABASE_URL` | |
| `SUPABASE_ANON_KEY` | |
| `SUPABASE_SERVICE_ROLE_KEY` | Required for Streamlit handoff table |
| `AUTH_WEB_URL` | **Vercel app URL** (https, no trailing slash) |
| `STREAMLIT_URL` | Fly Streamlit app URL |
| `SERVE_AUTH_UI` | `false` |
| `CORS_ALLOWED_ORIGINS` | Optional Vercel preview URLs |
| `MASTER_WORKBOOK_BUCKET` | etc. |

Health check: `GET https://your-api.fly.dev/api/health`

Default machine: 512MB RAM (`deploy/fly-api.toml`). Scale in Fly dashboard if needed.

## Fly.io Streamlit app

1. `fly apps create ali-al-baker-streamlit`
2. `fly deploy --config deploy/fly-streamlit.toml`
3. Secrets via `fly secrets set -c deploy/fly-streamlit.toml ...`

| Variable | Notes |
|----------|--------|
| `SUPABASE_URL` | |
| `SUPABASE_ANON_KEY` | |
| `AUTH_WEB_URL` | **Fly API URL** (not Vercel) |
| `STREAMLIT_URL` | This app’s public URL |
| Workbook buckets | Same as local `secrets.toml` |

Default machine: 1GB RAM (pandas / workbook load).

## Vercel (`auth_web`)

1. Root Directory: `auth_web`.
2. Framework: Vite (`auth_web/vercel.json`).
3. Build-time env (redeploy after changes):

| Variable | Example |
|----------|---------|
| `VITE_SUPABASE_URL` | `https://xxx.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | anon JWT |
| `VITE_API_URL` | `https://ali-al-baker-api.fly.dev` — **API only**, no `/api` suffix |
| `VITE_STREAMLIT_URL` | `https://ali-al-baker-streamlit.fly.dev` |

## Auth troubleshooting

| Symptom | Fix |
|---------|-----|
| Register / API errors | `VITE_API_URL` = Fly **API** URL; redeploy Vercel |
| Financials 404 | Same — not Streamlit URL, no `/api` suffix |
| Sign-in bounce | Confirm email; match Supabase keys on Vercel + Fly |
| CORS errors | `AUTH_WEB_URL` on Fly API = exact Vercel URL |

**Supabase → Authentication → URL Configuration:** Site URL = Vercel URL; redirect URLs include Vercel + `http://localhost:5173`.

## Local development

`python start.py` or separate API + Streamlit. Env optional; defaults use `.streamlit/secrets.toml`.

## CI / redeploy

```bash
fly deploy --config deploy/fly-api.toml
fly deploy --config deploy/fly-streamlit.toml
```

Vercel redeploys on git push if connected, or `vercel --prod` from `auth_web`.

## Legacy Railway

See `deploy/railway-*.toml` and old `deploy/VERCEL_RAILWAY.md` if needed; Fly is the supported production host for Python services.
