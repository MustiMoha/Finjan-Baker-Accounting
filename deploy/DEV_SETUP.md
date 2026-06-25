# Finjan Baker — Vercel + Railway setup

Supabase is already configured. Deploy the repo and set the variables below.

**Repo:** [https://github.com/MustiMoha/Finjan-Baker-Accounting](https://github.com/MustiMoha/Finjan-Baker-Accounting)

After deploy you will have three URLs — fill them in everywhere marked `YOUR_VERCEL_URL`, `YOUR_API_URL`, `YOUR_STREAMLIT_URL`.

---

## Shared credentials (copy into Railway / Vercel)


| Key                         | Value                                                                                                                                                                                                                       |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SUPABASE_URL`              | `https://cafomnrnrniqigzvbhho.supabase.co`                                                                                                                                                                                  |
| `SUPABASE_ANON_KEY`         | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNhZm9tbnJucm5pcWlnenZiaGhvIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzgwNjM1ODQsImV4cCI6MjA5MzYzOTU4NH0.-_3pOqVZzSqooes7870v3lZkvjmYDA_GZXdmu8ULJ8E`          |
| `SUPABASE_SERVICE_ROLE_KEY` | Ask repo owner (Supabase Dashboard → Settings → API). Never commit this key. |
| `MASTER_WORKBOOK_BUCKET`    | `accounting-master`                                                                                                                                                                                                         |
| `DOCUMENTS_BUCKET`          | `accounting-documents`                                                                                                                                                                                                      |


---

## 1. Railway — API (first service)

1. Deploy from GitHub → **root directory** = repo root (not `api/`).
2. **Config path:** leave default (`railway.toml` at repo root) or set start command: `bash deploy/start-api.sh`
   (Nixpacks defaults to `uvicorn main:app`; root `main.py` re-exports the FastAPI app.)
3. **Networking** → public domain → `YOUR_API_URL`
4. **Variables:**


| Variable                    | Value                                              |
| --------------------------- | -------------------------------------------------- |
| `SUPABASE_URL`              | `https://cafomnrnrniqigzvbhho.supabase.co`         |
| `SUPABASE_ANON_KEY`         | (anon key in table above)                          |
| `SUPABASE_SERVICE_ROLE_KEY` | (from project owner)                               |
| `AUTH_WEB_URL`              | `YOUR_VERCEL_URL` — set after Vercel deploy        |
| `STREAMLIT_URL`             | `YOUR_STREAMLIT_URL` — set after Streamlit service |
| `SERVE_AUTH_UI`             | `false`                                            |
| `MASTER_WORKBOOK_BUCKET`    | `accounting-master`                                |
| `DOCUMENTS_BUCKET`          | `accounting-documents`                             |


1. Test: `YOUR_API_URL/api/health` → `{"status":"ok"}`

---

## 2. Railway — Streamlit (second service)

1. Same repo → add **second service**.
2. **Config path:** `deploy/railway-streamlit.toml` (do not use root `railway.toml` — that starts the API).
3. **Start command:** `bash deploy/start-streamlit.sh` (if not using the streamlit config file).
3. Public domain → `YOUR_STREAMLIT_URL`
4. **Variables:**


| Variable                 | Value                                      |
| ------------------------ | ------------------------------------------ |
| `SUPABASE_URL`           | `https://cafomnrnrniqigzvbhho.supabase.co` |
| `SUPABASE_ANON_KEY`      | (anon key in table above)                  |
| `AUTH_WEB_URL`           | `YOUR_API_URL` ← **API URL, not Vercel**   |
| `STREAMLIT_URL`          | `YOUR_STREAMLIT_URL`                       |
| `MASTER_WORKBOOK_BUCKET` | `accounting-master`                        |
| `DOCUMENTS_BUCKET`       | `accounting-documents`                     |


1. Update API service `STREAMLIT_URL` if you deployed API first.

---

## 3. Vercel — React app

1. Import GitHub repo.
2. **Root directory:** `auth_web`
3. **Framework:** Vite
4. **Environment variables** (Production — redeploy after any change):


| Variable                 | Value                                      |
| ------------------------ | ------------------------------------------ |
| `VITE_SUPABASE_URL`      | `https://cafomnrnrniqigzvbhho.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | (anon key in table above)                  |
| `VITE_API_URL`           | `YOUR_API_URL` (no trailing slash)         |
| `VITE_STREAMLIT_URL`     | `YOUR_STREAMLIT_URL`                       |


1. Deploy → `YOUR_VERCEL_URL`
2. Set Railway **API** `AUTH_WEB_URL` = `YOUR_VERCEL_URL`

---

## URL cheat sheet


| Variable        | Railway API   | Railway Streamlit  | Vercel               |
| --------------- | ------------- | ------------------ | -------------------- |
| `AUTH_WEB_URL`  | Vercel URL    | **API URL**        | —                    |
| `STREAMLIT_URL` | Streamlit URL | same Streamlit URL | `VITE_STREAMLIT_URL` |
| API calls       | —             | —                  | `VITE_API_URL`       |


---

## Quick test

1. Open Vercel URL → sign in.
2. Dashboard loads.
3. **Financials** opens Streamlit.

**Common fixes:** CORS → API `AUTH_WEB_URL` must match Vercel URL exactly. Financials auth fails → Streamlit `AUTH_WEB_URL` must be API URL, not Vercel.

---

**Note:** Share this file privately. Do not commit service-role keys to git.