-- Migration: 20260927100000_teachers_auth_user_id.sql
-- Description: Link public.teachers to Supabase Auth (no passwords, no RLS)

ALTER TABLE public.teachers
  ADD COLUMN IF NOT EXISTS auth_user_id UUID UNIQUE REFERENCES auth.users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS teachers_auth_user_id_idx
  ON public.teachers (auth_user_id);

COMMENT ON COLUMN public.teachers.auth_user_id IS
  'Links teacher profile to Supabase Auth user. Passwords live only in auth.users.';
