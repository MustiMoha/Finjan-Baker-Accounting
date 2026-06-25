-- Profiles (mirror auth.users emails for admin UX), audit sign-ins, admin RLS for user_roles/profiles.

-- ---------------------------------------------------------------------------
-- public.profiles
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
  email TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_profiles_updated ON public.profiles (updated_at DESC);

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.sync_profile_from_auth()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id, email, updated_at)
  VALUES (NEW.id, NEW.email, now())
  ON CONFLICT (id) DO UPDATE
    SET email = EXCLUDED.email,
        updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_profile_sync ON auth.users;
CREATE TRIGGER on_auth_user_profile_sync
  AFTER INSERT OR UPDATE OF email ON auth.users
  FOR EACH ROW
  EXECUTE PROCEDURE public.sync_profile_from_auth();

INSERT INTO public.profiles (id, email, updated_at)
SELECT id, email, now()
FROM auth.users
ON CONFLICT (id) DO UPDATE
  SET email = EXCLUDED.email,
      updated_at = now();

DROP POLICY IF EXISTS profiles_select_own_or_admin ON public.profiles;
CREATE POLICY profiles_select_own_or_admin ON public.profiles
  FOR SELECT TO authenticated
  USING (id = auth.uid() OR public.has_role(ARRAY['admin']));

DROP POLICY IF EXISTS profiles_update_admin ON public.profiles;
CREATE POLICY profiles_update_admin ON public.profiles
  FOR UPDATE TO authenticated
  USING (public.has_role(ARRAY['admin']))
  WITH CHECK (public.has_role(ARRAY['admin']));

GRANT SELECT, UPDATE ON public.profiles TO authenticated;

-- ---------------------------------------------------------------------------
-- public.audit_sign_ins (Streamlit login path)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.audit_sign_ins (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  email TEXT,
  role TEXT,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  user_agent TEXT,
  client_ip TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_sign_ins_occurred ON public.audit_sign_ins (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_sign_ins_user ON public.audit_sign_ins (user_id);

ALTER TABLE public.audit_sign_ins ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS audit_sign_ins_insert_own ON public.audit_sign_ins;
CREATE POLICY audit_sign_ins_insert_own ON public.audit_sign_ins
  FOR INSERT TO authenticated
  WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS audit_sign_ins_select_admin ON public.audit_sign_ins;
CREATE POLICY audit_sign_ins_select_admin ON public.audit_sign_ins
  FOR SELECT TO authenticated
  USING (public.has_role(ARRAY['admin']));

GRANT SELECT, INSERT ON public.audit_sign_ins TO authenticated;

-- ---------------------------------------------------------------------------
-- user_roles: allow admin read/update/all rows
-- ---------------------------------------------------------------------------
DROP POLICY IF EXISTS user_roles_select_own ON public.user_roles;
CREATE POLICY user_roles_select_own ON public.user_roles
  FOR SELECT TO authenticated
  USING (
    user_id = auth.uid()
    OR public.has_role(ARRAY['admin'])
  );

DROP POLICY IF EXISTS user_roles_insert_admin ON public.user_roles;
CREATE POLICY user_roles_insert_admin ON public.user_roles
  FOR INSERT TO authenticated
  WITH CHECK (public.has_role(ARRAY['admin']));

DROP POLICY IF EXISTS user_roles_update_admin ON public.user_roles;
CREATE POLICY user_roles_update_admin ON public.user_roles
  FOR UPDATE TO authenticated
  USING (public.has_role(ARRAY['admin']))
  WITH CHECK (public.has_role(ARRAY['admin']));
