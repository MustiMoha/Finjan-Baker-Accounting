# Deployment

| Doc | Audience |
|-----|----------|
| [DEV_SETUP.md](DEV_SETUP.md) | Quick env + deploy checklist for Mustafa |
| [VERCEL_FLY.md](VERCEL_FLY.md) | Full Vercel + Fly.io + Supabase reference |

## Fly.io (production Python)

```bash
fly deploy                              # API (uses root fly.toml)
fly deploy --config deploy/fly-streamlit.toml
```

Configs: `deploy/fly-api.toml`, `deploy/fly-streamlit.toml`  
Docker: `deploy/Dockerfile.api`, `deploy/Dockerfile.streamlit`

## Vercel (React)

Root directory: `auth_web` — see DEV_SETUP.md.

## Legacy Railway

`deploy/railway-*.toml` — deprecated; use Fly.io instead.
