-- Document optional header_first_row in gl_layout_json (schema unchanged).

COMMENT ON COLUMN public.app_settings.gl_layout_json IS
  '{"mode":"auto"|"manual","header_first_row":1,"data_start_row":2,"columns":{"date":0,"details":1,"particulars":2,"debit":3,"credit":4,"currency":null,"tr_number":null}} — header_first_row/data_start_row bound the header band for scan + manual column picks; when mode is manual, columns are used for read and approve-post.';
