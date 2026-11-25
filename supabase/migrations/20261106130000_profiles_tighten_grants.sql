-- Supabase default grants left TRUNCATE / REFERENCES / TRIGGER on profiles for API roles.
-- TRUNCATE bypasses RLS, so remove them. authenticated keeps SELECT + UPDATE (full_name) only.
revoke truncate, references, trigger on public.profiles from anon, authenticated;
