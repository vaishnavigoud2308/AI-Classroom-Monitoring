from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class AttendanceResponse(BaseModel):
    id: str
    student_id: str
    session_id: str
    status: str
    confidence: Optional[float] = None
    manually_corrected: bool = False
    created_at: datetime

class AttendanceUpdateRequest(BaseModel):
    status: str  # Present | Absent | Late
