import os
import sys
import time
import datetime

# Ensure sys.path includes module parent directories
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from config import get_supabase_client
from monitoring_config import MonitoringConfig

class AlertEngine:
    """
    Receives raw activity events from the monitoring modules (like ClassroomActivityDetector)
    and converts them into teacher-facing SQL alerts stored in Supabase.
    
    Includes an active cooldown cache to suppress spam and checks feature toggles.
    """
    def __init__(self, config=None, supabase_client=None):
        self.config = config or MonitoringConfig()
        
        # Allows for mocked dependency injection during tests
        # If None is explicitly passed (or not provided during prod), it gets the actual client.
        if supabase_client is not False: 
            self.supabase = supabase_client or get_supabase_client()
        else:
            self.supabase = None # explicit Disable For Mock
            
        # (student_id, activity) -> float (timestamp)
        self._cooldown_cache = {}

        # Defines how internal activity names map to user-friendly messages and config settings
        self.ALERT_MAP = {
            "phone_usage": {
                "message": "Phone Usage Detected",
                "enabled_flag": "phone_detection_enabled",
                "cooldown_attr": "cooldown_phone_usage"
            },
            "sleeping": {
                "message": "Possible Sleeping",
                "enabled_flag": "sleeping_detection_enabled",
                "cooldown_attr": "cooldown_sleeping"
            },
            "looking_away": {
                "message": "Looking Away Detected",
                "enabled_flag": "looking_away_detection_enabled",
                "cooldown_attr": "cooldown_looking_away"
            },
            "unnecessary_activity": {
                "message": "Unnecessary Activity Detected",
                "enabled_flag": "unnecessary_activity_enabled",
                "cooldown_attr": "cooldown_unnecessary_activity"
            },
            "prolonged_discussion": {
                "message": "Possible Prolonged Discussion",
                "enabled_flag": "talking_detection_enabled",
                "cooldown_attr": "cooldown_prolonged_discussion"
            },
            "excessive_noise": {
                "message": "Excessive Classroom Noise Detected",
                "enabled_flag": "audio_monitoring_enabled",
                "cooldown_attr": "cooldown_excessive_noise"
            }
        }

    def process_activity_event(self, session_id, event_payload, current_time=None):
        """
        Processes a raw event payload. If it's an actionable alert, evaluates cooldowns,
        and saves it to the database.
        
        event_payload example:
        {
          "student_id": "uuid-here" | None,
          "activity": "excessive_noise" | "phone_usage",
          "confidence": 95.0,
          "details": {...},
          "timestamp": "iso-time"
        }
        
        Returns a boolean indicating if an alert was actually generated and pushed to the DB.
        """
        if current_time is None:
            current_time = time.time()

        activity = event_payload.get("activity")
        student_id = event_payload.get("student_id")
        confidence = event_payload.get("confidence", 0.0)

        # 1. Ignore normal, unknown, or completely unmapped activities
        if activity in ("normal", "unknown", "talking") or activity not in self.ALERT_MAP:
            return False

        mapping = self.ALERT_MAP[activity]
        
        # 2. Independent Feature Toggle check
        is_enabled = getattr(self.config, mapping["enabled_flag"], False)
        if not is_enabled:
            return False

        # 3. Cooldown check
        # For room-wide alerts without student_id, key on ("CLASSROOM_WIDE", activity)
        cache_key = (student_id if student_id not in ("UNKNOWN_STUDENT", None, "") else "CLASSROOM_WIDE", activity)
        last_alert_time = self._cooldown_cache.get(cache_key, -float("inf"))
        cooldown_duration = getattr(self.config, mapping["cooldown_attr"], 60.0)

        if (current_time - last_alert_time) < cooldown_duration:
            # We are within the cooldown period. Drop the alert to avoid spam.
            return False

        # 4. Generate the neutral alert description
        description = mapping["message"]
        
        # 5. Persist to Supabase
        if self.supabase:
            try:
                row = {
                    "session_id": session_id,
                    "student_id": student_id if student_id not in ("UNKNOWN_STUDENT", None, "") else None,
                    "alert_type": activity,
                    "description": description,
                    "confidence": float(min(100.0, max(0.0, float(confidence)))) if confidence is not None else None,
                    "status": "New",
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }
                # Insert into the existing classroom_alerts table
                self.supabase.table("classroom_alerts").insert(row).execute()
            except Exception as e:
                print(f"[AlertEngine] Error pushing alert to Supabase: {e}")
                return False

        # Update cache after successful (or simulated) insert
        self._cooldown_cache[cache_key] = current_time
        return True
