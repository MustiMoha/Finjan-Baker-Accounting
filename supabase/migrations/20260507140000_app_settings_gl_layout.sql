-- Optional GL sheet layout: manual column indices (0-based) or auto-detect fallback.

ALTER TABLE public.app_settings
  ADD COLUMN IF NOT EXISTS gl_layout_json JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN public.app_settings.gl_layout_json IS
  '{"mode":"auto"|"manual","data_start_row":2,"columns":{"date":0,"details":1,"particulars":2,"debit":3,"credit":4,"currency":null}} — when mode is manual, columns are used for read and approve-post.';
