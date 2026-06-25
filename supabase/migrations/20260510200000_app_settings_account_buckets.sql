alter table public.app_settings add column if not exists account_buckets_json jsonb not null default '{"mappings":[]}'::jsonb;
