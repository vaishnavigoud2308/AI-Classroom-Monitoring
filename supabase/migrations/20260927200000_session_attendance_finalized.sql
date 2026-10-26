-- Migration: 20260927200000_session_attendance_finalized.sql
-- Description: Minimal addition to track attendance finalized state and timestamp for class_sessions

ALTER TABLE public.class_sessions
  ADD COLUMN IF NOT EXISTS attendance_finalized BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS attendance_submitted_at TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN public.class_sessions.attendance_finalized IS
  'Indicates if the attendance sheet for this session has been finalized and submitted by the teacher.';

COMMENT ON COLUMN public.class_sessions.attendance_submitted_at IS
  'Timestamp when attendance was submitted and locked.';
