-- Let org owners/admins/delegated approvers read profiles for members in the same org.

DROP POLICY IF EXISTS profiles_select_own_or_admin ON public.profiles;
CREATE POLICY profiles_select_own_or_admin ON public.profiles
  FOR SELECT TO authenticated
  USING (
    id = auth.uid()
    OR public.has_role(ARRAY['admin'])
    OR EXISTS (
      SELECT 1
      FROM public.org_members me
      JOIN public.org_members them ON them.org_id = me.org_id
      WHERE me.user_id = auth.uid()
        AND me.status = 'active'
        AND (
          me.org_role IN ('owner', 'admin')
          OR me.can_approve = true
        )
        AND them.user_id = profiles.id
    )
  );
