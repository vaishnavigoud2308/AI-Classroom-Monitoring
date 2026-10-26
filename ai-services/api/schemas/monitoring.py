from pydantic import BaseModel
from typing import Optional, Any

class MonitoringConfigSchema(BaseModel):
    attendance_enabled: bool = True
    phone_detection_enabled: bool = True
    talking_detection_enabled: bool = True
    audio_monitoring_enabled: bool = True
    sleeping_detection_enabled: bool = True
    looking_away_detection_enabled: bool = True
    unnecessary_activity_enabled: bool = True

class MonitoringStatusSchema(BaseModel):
    is_active: bool
    current_session_id: Optional[str] = None
    enabled_features: MonitoringConfigSchema
    camera_status: str = "stopped"
    camera_error: Optional[str] = None
    audio_status: str = "stopped"
    audio_error: Optional[str] = None
    current_sound_level_db: float = 0.0
    smoothed_sound_level_db: float = 0.0
    frames_processed: int = 0
    last_frame_at: Optional[str] = None
    is_monitoring: bool = False
    recognizer_trained: bool = False
    last_recognized: Optional[Any] = None
