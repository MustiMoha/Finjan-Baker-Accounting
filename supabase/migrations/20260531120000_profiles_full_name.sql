-- Display name on profiles; users may update their own name.

ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS full_name TEXT;

DROP POLICY IF EXISTS profiles_update_own ON public.profiles;
CREATE POLICY profiles_update_own ON public.profiles
  FOR UPDATE TO authenticated
  USING (id = auth.uid())
  WITH CHECK (id = auth.uid());
