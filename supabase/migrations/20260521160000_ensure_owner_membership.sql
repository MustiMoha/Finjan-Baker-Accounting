-- Fix owners without org_members rows (gate stuck on "none") and let owners read their org.

CREATE OR REPLACE FUNCTION public.ensure_owner_org_membership()
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_uid UUID := auth.uid();
  v_org public.organizations;
  v_settings_id SMALLINT;
BEGIN
  IF v_uid IS NULL THEN
    RETURN false;
  END IF;

  IF EXISTS (
    SELECT 1 FROM public.org_members m
    WHERE m.user_id = v_uid AND m.status = 'active'
  ) THEN
    RETURN true;
  END IF;

  SELECT * INTO v_org
  FROM public.organizations o
  WHERE o.owner_user_id = v_uid
  ORDER BY o.created_at DESC
  LIMIT 1;

  IF NOT FOUND THEN
    RETURN false;
  END IF;

  INSERT INTO public.org_members (
    org_id, user_id, org_role, job_title, status, can_approve
  )
  VALUES (v_org.id, v_uid, 'owner', 'Owner', 'active', true)
  ON CONFLICT (org_id, user_id) DO UPDATE
    SET org_role = 'owner',
        status = 'active',
        can_approve = true,
        updated_at = now();

  INSERT INTO public.user_roles (user_id, role)
  VALUES (v_uid, 'admin')
  ON CONFLICT (user_id) DO UPDATE SET role = 'admin';

  IF NOT EXISTS (SELECT 1 FROM public.app_settings WHERE org_id = v_org.id) THEN
    SELECT COALESCE(MAX(id), 0) + 1 INTO v_settings_id FROM public.app_settings;
    INSERT INTO public.app_settings (id, org_id, fiscal_year_start_month, updated_by)
    VALUES (v_settings_id, v_org.id, 1, v_uid);
  END IF;

  RETURN true;
END;
$$;

GRANT EXECUTE ON FUNCTION public.ensure_owner_org_membership() TO authenticated;

DROP POLICY IF EXISTS organizations_select_member ON public.organizations;
CREATE POLICY organizations_select_member ON public.organizations
  FOR SELECT TO authenticated
  USING (
    owner_user_id = auth.uid()
    OR public.is_active_org_member(id)
    OR EXISTS (
      SELECT 1 FROM public.org_members m
      WHERE m.org_id = organizations.id AND m.user_id = auth.uid()
    )
  );
