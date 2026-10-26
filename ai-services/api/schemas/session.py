from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class SessionStartRequest(BaseModel):
    teacher_name: str = "Demo Teacher"
    subject: str = "Live Monitoring API"
    classroom: str = "Room API-01"

class SessionResponse(BaseModel):
    id: str
    teacher_id: str
    subject: str
    classroom: str
    start_time: datetime
    end_time: Optional[datetime] = None
    attendance_finalized: Optional[bool] = False
    attendance_submitted_at: Optional[datetime] = None
    created_at: datetime

