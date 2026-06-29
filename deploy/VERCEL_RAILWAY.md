# Vercel (auth_web) + Railway (API + Streamlit) + Supabase

## Architecture

| Component | Host | Root / command |
|-----------|------|----------------|
| React app | **Vercel** | Root directory: `auth_web` (preset: Vite) |
| FastAPI API | **Railway** | `deploy/start-api.sh` |
| Streamlit Financials | **Railway** (2nd service) | `deploy/start-streamlit.sh` |
| Database / auth / storage | **Supabase** | — |

Apply migration `20260610120000_streamlit_handoff_codes.sql` so API handoff works across Railway replicas.

## Vercel (`auth_web`)

1. Import repo; set **Root Directory** to `auth_web`.
2. Framework preset: **Vite** (or use `auth_web/vercel.json`).
3. Environment variables (Production):

| Variable | Example |
|----------|---------|
| `VITE_SUPABASE_URL` | `https://xxx.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | anon key |
| `VITE_API_URL` | `https://your-api.up.railway.app` |
| `VITE_STREAMLIT_URL` | `https://your-streamlit.up.railway.app` |

**Important:** `VITE_*` values are embedded at build time. After adding or changing them, trigger a new Vercel deployment.

## Auth troubleshooting (sign-in / register)

| Symptom | Likely cause | Fix |
|---------|----------------|-----|
| Register: “Request failed” | `VITE_API_URL` missing or wrong on Vercel | Set to Railway API URL; redeploy Vercel |
| Sign-in: “Invalid credentials” | Wrong password, or email not confirmed | Confirm email in inbox/spam; or disable “Confirm email” in Supabase → Auth → Providers → Email (dev only) |
| Sign-in works locally but not on Vercel | Vercel `VITE_SUPABASE_*` ≠ Railway `SUPABASE_*` | Use the same project URL and anon key everywhere |
| API errors after sign-in | `AUTH_WEB_URL` on Railway ≠ Vercel URL | Set `AUTH_WEB_URL` to exact Vercel URL (https, no trailing slash) |

**Supabase Dashboard → Authentication → URL Configuration**

- **Site URL:** your Vercel production URL  
- **Redirect URLs:** Vercel URL and `http://localhost:5173` for local dev

**Supabase → Authentication → Providers → Email:** default SMTP allows only ~2 emails/hour. For testing many sign-ups, configure custom SMTP or temporarily turn off “Confirm email”.

## Railway API service

1. New service from same repo; use `deploy/railway-api.toml` or set **Start Command**: `bash deploy/start-api.sh`
2. **Build**: `pip install -r requirements.txt`
3. Environment variables:

| Variable | Notes |
|----------|--------|
| `SUPABASE_URL` | |
| `SUPABASE_ANON_KEY` | |
| `SUPABASE_SERVICE_ROLE_KEY` | Required for Streamlit handoff table |
| `AUTH_WEB_URL` | **Vercel app URL** (e.g. `https://app.vercel.app`) |
| `STREAMLIT_URL` | Railway Streamlit service URL |
| `CORS_ALLOWED_ORIGINS` | Optional; comma-separated extra origins (Vercel preview URLs) |
| `SERVE_AUTH_UI` | `false` (API-only; UI on Vercel) |
| `MASTER_WORKBOOK_BUCKET` | etc. |

Health check: `GET /api/health`

## Railway Streamlit service

1. Second service; **Start Command**: `bash deploy/start-streamlit.sh`
2. Same Supabase + workbook env vars as local `secrets.toml`.
3. `AUTH_WEB_URL` must be the **Railway API URL** (Streamlit calls `/api/streamlit/exchange`).

| Variable | Notes |
|----------|--------|
| `SUPABASE_URL` | |
| `SUPABASE_ANON_KEY` | |
| `AUTH_WEB_URL` | **Railway API URL** (not Vercel) |
| `STREAMLIT_URL` | This service’s public URL |

## Local development

Unchanged: `python start.py` or API + Streamlit separately. Env vars optional; defaults use `.streamlit/secrets.toml`.

## Optional: preview deployments

Add Vercel preview URLs to Railway `CORS_ALLOWED_ORIGINS` or use a wildcard pattern manually per preview.
