-- Onboarding RPCs: run as definer so inserts succeed with the caller's auth.uid().

CREATE OR REPLACE FUNCTION public.create_organization_with_owner(
  p_name TEXT,
  p_job_title TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_uid UUID := auth.uid();
  v_code CHAR(6);
  v_org public.organizations;
  v_name TEXT := trim(p_name);
  v_title TEXT := trim(p_job_title);
  v_settings_id SMALLINT;
BEGIN
  IF v_uid IS NULL THEN
    RAISE EXCEPTION 'Not authenticated';
  END IF;

  IF char_length(v_name) < 2 THEN
    RAISE EXCEPTION 'Organization name must be at least 2 characters.';
  END IF;

  IF v_title = '' THEN
    RAISE EXCEPTION 'Enter your role title (e.g. CFO, Controller).';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.org_members m
    WHERE m.user_id = v_uid
      AND m.status IN ('active', 'pending')
  ) THEN
    RAISE EXCEPTION 'You already belong to an organization or have a pending request.';
  END IF;

  v_code := public.generate_unique_join_code();

  INSERT INTO public.organizations (name, join_code, owner_user_id)
  VALUES (v_name, v_code, v_uid)
  RETURNING * INTO v_org;

  INSERT INTO public.org_members (
    org_id, user_id, org_role, job_title, status, can_approve
  )
  VALUES (v_org.id, v_uid, 'owner', v_title, 'active', true);

  SELECT COALESCE(MAX(id), 0) + 1 INTO v_settings_id FROM public.app_settings;

  INSERT INTO public.app_settings (id, org_id, fiscal_year_start_month, updated_by)
  VALUES (v_settings_id, v_org.id, 1, v_uid);

  RETURN to_jsonb(v_org);
END;
$$;

CREATE OR REPLACE FUNCTION public.request_join_organization_by_code(
  p_join_code TEXT,
  p_job_title TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_uid UUID := auth.uid();
  v_code TEXT := upper(trim(p_join_code));
  v_title TEXT := trim(p_job_title);
  v_org public.organizations;
  v_member public.org_members;
BEGIN
  IF v_uid IS NULL THEN
    RAISE EXCEPTION 'Not authenticated';
  END IF;

  IF char_length(v_code) <> 6 OR v_code !~ '^[A-Z0-9]{6}$' THEN
    RAISE EXCEPTION 'Enter a valid 6-character join code.';
  END IF;

  IF v_title = '' THEN
    RAISE EXCEPTION 'Enter your role title.';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.org_members m
    WHERE m.user_id = v_uid
      AND m.status IN ('active', 'pending')
  ) THEN
    RAISE EXCEPTION 'You already have an active or pending membership.';
  END IF;

  SELECT * INTO v_org
  FROM public.organizations o
  WHERE o.join_code = v_code
  LIMIT 1;

  IF v_org.id IS NULL THEN
    RAISE EXCEPTION 'No organization found for that join code.';
  END IF;

  INSERT INTO public.org_members (
    org_id, user_id, org_role, job_title, status, can_approve
  )
  VALUES (v_org.id, v_uid, 'user', v_title, 'pending', false)
  RETURNING * INTO v_member;

  RETURN jsonb_build_object(
    'org_id', v_member.org_id,
    'status', v_member.status,
    'id', v_member.id
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.create_organization_with_owner(TEXT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION public.request_join_organization_by_code(TEXT, TEXT) TO authenticated;
