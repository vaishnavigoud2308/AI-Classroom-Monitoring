import uuid
import datetime
import os
import sys

# Ensure config is available
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from config import get_supabase_client

class MonitoringSessionManager:
    """
    Manages the creation and retrieval of the live classroom monitoring session.
    This safely creates an entry in public.class_sessions preventing the need for seed_dev_data.
    It can be easily replaced or tied to FastAPI endpoints later.
    """
    def __init__(self, supabase_client=None):
        if supabase_client is not False: 
            self.supabase = supabase_client or get_supabase_client()
        else:
            self.supabase = None
        self.session_id = None
        self.teacher_id = None
        # In-memory tracking of submitted/finalized sessions: session_id -> metadata
        self.finalized_sessions = {}

    def finalize_session(self, session_id, teacher_id=None, submitted_at=None):
        """Marks a session attendance as finalized in-memory and returns metadata."""
        if not submitted_at:
            submitted_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.finalized_sessions[session_id] = {
            "session_id": session_id,
            "submitted_at": submitted_at,
            "teacher_id": teacher_id or self.teacher_id,
        }
        return self.finalized_sessions[session_id]

    def is_session_finalized(self, session_id):
        """Checks if a session attendance has already been finalized/submitted."""
        if not session_id:
            return False
        if session_id in self.finalized_sessions:
            return True
        if self.supabase:
            try:
                res = self.supabase.table("class_sessions").select("attendance_finalized").eq("id", session_id).execute()
                if res.data and len(res.data) > 0:
                    val = res.data[0].get("attendance_finalized")
                    if bool(val):
                        self.finalized_sessions[session_id] = {"session_id": session_id, "submitted_at": None}
                        return True
            except Exception:
                pass
        return False
        
    def start_or_get_session(self, teacher_name="Demo Teacher", subject="Live Monitoring API", classroom="Room API-01"):
        """
        Ensures a valid teacher exists and creates a new class_session 
        for the current realtime monitoring run.
        """
        if not self.supabase:
            # Mock behavior for testing
            self.session_id = "test-mock-session"
            return self.session_id

        try:
            # 1. Get or create teacher securely
            teacher_res = self.supabase.table("teachers").select("*").eq("name", teacher_name).execute()
            if teacher_res.data and len(teacher_res.data) > 0:
                self.teacher_id = teacher_res.data[0]["id"]
            else:
                # Prevent unique email collisions by appending timestamp logic in a safe way if needed, 
                # but for 'Demo Teacher' we just use a static mock email fallback.
                email = f"{teacher_name.replace(' ', '.').lower()}.live@example.com"
                
                # Double check email
                email_res = self.supabase.table("teachers").select("*").eq("email", email).execute()
                if email_res.data and len(email_res.data) > 0:
                    self.teacher_id = email_res.data[0]["id"]
                else:
                    new_teacher = {
                        "name": teacher_name,
                        "email": email
                    }
                    insert_res = self.supabase.table("teachers").insert(new_teacher).execute()
                    self.teacher_id = insert_res.data[0]["id"]
                
            # 2. Create the session
            new_session = {
                "teacher_id": self.teacher_id,
                "subject": subject,
                "classroom": classroom,
                "start_time": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            session_res = self.supabase.table("class_sessions").insert(new_session).execute()
            self.session_id = session_res.data[0]["id"]
            
            return self.session_id
        except Exception as e:
            print(f"[SessionManager] Failed to create monitoring session: {e}")
            self.session_id = "offline-fallback-session"
            return self.session_id
