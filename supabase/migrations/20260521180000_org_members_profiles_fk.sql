-- Let PostgREST embed profiles on org_members (profiles.id = auth.users.id = org_members.user_id).

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'org_members_user_id_profiles_fkey'
  ) THEN
    ALTER TABLE public.org_members
      ADD CONSTRAINT org_members_user_id_profiles_fkey
      FOREIGN KEY (user_id) REFERENCES public.profiles (id) ON DELETE CASCADE;
  END IF;
END $$;
