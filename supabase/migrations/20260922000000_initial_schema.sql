-- Migration: 20260922000000_initial_schema.sql
-- Description: Initial schema for AI-Powered Classroom Monitoring System

-- 1. teachers
CREATE TABLE IF NOT EXISTS public.teachers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. students
CREATE TABLE IF NOT EXISTS public.students (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    roll_number TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE,
    face_image_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. class_sessions
CREATE TABLE IF NOT EXISTS public.class_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    teacher_id UUID NOT NULL REFERENCES public.teachers(id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    classroom TEXT NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. attendance
CREATE TABLE IF NOT EXISTS public.attendance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES public.students(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES public.class_sessions(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('Present', 'Absent', 'Late')),
    confidence NUMERIC CHECK (confidence >= 0 AND confidence <= 100),
    manually_corrected BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (student_id, session_id) -- Ensure one attendance record per student per session
);

-- 5. classroom_alerts
CREATE TABLE IF NOT EXISTS public.classroom_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.class_sessions(id) ON DELETE CASCADE,
    student_id UUID REFERENCES public.students(id) ON DELETE SET NULL, -- student_id is nullable
    alert_type TEXT NOT NULL, -- e.g., 'mobile_phone_detected', 'sleeping_detected', 'excessive_noise'
    description TEXT,
    confidence NUMERIC CHECK (confidence >= 0 AND confidence <= 100),
    status TEXT NOT NULL DEFAULT 'New' CHECK (status IN ('New', 'Reviewed', 'Dismissed')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
