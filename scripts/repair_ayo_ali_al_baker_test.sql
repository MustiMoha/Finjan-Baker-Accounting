-- Repair: link ayo@zaun.dev to "Ali Al Baker Test" as owner/admin.
-- Run in Supabase Dashboard → SQL Editor (uses postgres superuser, bypasses RLS).

DO $$
DECLARE
  v_email TEXT := 'ayo@zaun.dev';
  v_org_name TEXT := 'Ali Al Baker Test';
  v_uid UUID;
  v_org_id UUID;
  v_settings_id SMALLINT;
BEGIN
  SELECT id INTO v_uid
  FROM auth.users
  WHERE lower(email) = lower(v_email)
  LIMIT 1;

  IF v_uid IS NULL THEN
    RAISE EXCEPTION 'No auth user for %', v_email;
  END IF;

  SELECT id INTO v_org_id
  FROM public.organizations
  WHERE name = v_org_name
  LIMIT 1;

  IF v_org_id IS NULL THEN
    RAISE EXCEPTION 'No organization named %. Check organizations.name in Table Editor.', v_org_name;
  END IF;

  UPDATE public.organizations
  SET owner_user_id = v_uid,
      updated_at = now()
  WHERE id = v_org_id;

  INSERT INTO public.org_members (
    org_id, user_id, org_role, job_title, status, can_approve
  )
  VALUES (v_org_id, v_uid, 'owner', 'Administrator', 'active', true)
  ON CONFLICT (org_id, user_id) DO UPDATE
    SET org_role = 'owner',
        status = 'active',
        can_approve = true,
        updated_at = now();

  INSERT INTO public.user_roles (user_id, role)
  VALUES (v_uid, 'admin')
  ON CONFLICT (user_id) DO UPDATE
    SET role = 'admin';

  IF NOT EXISTS (SELECT 1 FROM public.app_settings WHERE org_id = v_org_id) THEN
    SELECT COALESCE(MAX(id), 0) + 1 INTO v_settings_id FROM public.app_settings;
    INSERT INTO public.app_settings (id, org_id, fiscal_year_start_month, updated_by)
    VALUES (v_settings_id, v_org_id, 1, v_uid);
  END IF;

  RAISE NOTICE 'Done: % is owner/admin of % (%)', v_email, v_org_name, v_org_id;
END $$;
