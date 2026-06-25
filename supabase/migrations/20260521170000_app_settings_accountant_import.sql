-- Allow accountants (and owners, via is_org_adminish) to update org app_settings e.g. gl_layout_json.

DROP POLICY IF EXISTS app_settings_update_admin ON public.app_settings;
CREATE POLICY app_settings_update_admin ON public.app_settings
  FOR UPDATE TO authenticated
  USING (
    (
      org_id IS NOT NULL
      AND public.is_active_org_member(org_id)
      AND (
        public.is_org_adminish(org_id)
        OR EXISTS (
          SELECT 1
          FROM public.org_members m
          WHERE m.org_id = app_settings.org_id
            AND m.user_id = auth.uid()
            AND m.status = 'active'
            AND m.org_role = 'accountant'
        )
      )
    )
    OR (org_id IS NULL AND public.has_role(ARRAY['admin']))
  )
  WITH CHECK (
    (
      org_id IS NOT NULL
      AND public.is_active_org_member(org_id)
      AND (
        public.is_org_adminish(org_id)
        OR EXISTS (
          SELECT 1
          FROM public.org_members m
          WHERE m.org_id = app_settings.org_id
            AND m.user_id = auth.uid()
            AND m.status = 'active'
            AND m.org_role = 'accountant'
        )
      )
    )
    OR (org_id IS NULL AND public.has_role(ARRAY['admin']))
  );
