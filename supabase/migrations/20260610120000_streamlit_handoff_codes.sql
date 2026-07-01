-- One-time Streamlit session handoff codes (API mints, Streamlit exchanges).
-- Service role only; survives multi-instance Fly.io API deploys.

create table if not exists public.streamlit_handoff_codes (
  code text primary key,
  access_token text not null,
  refresh_token text not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now()
);

create index if not exists streamlit_handoff_codes_expires_at_idx
  on public.streamlit_handoff_codes (expires_at);

alter table public.streamlit_handoff_codes enable row level security;

comment on table public.streamlit_handoff_codes is
  'Short-lived Baker → Streamlit auth handoff; accessed only via service role from the API.';
