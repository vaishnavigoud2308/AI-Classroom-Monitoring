from pydantic import BaseModel
from typing import Optional

class MonitoringConfigSchema(BaseModel):
    attendance_enabled: bool
    phone_detection_enabled: bool
    talking_detection_enabled: bool
    sleeping_detection_enabled: bool
    looking_away_detection_enabled: bool
    unnecessary_activity_enabled: bool

class MonitoringStatusSchema(BaseModel):
    is_active: bool
    current_session_id: Optional[str] = None
    enabled_features: MonitoringConfigSchema
