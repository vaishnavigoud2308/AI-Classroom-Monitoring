from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class AlertResponse(BaseModel):
    id: str
    session_id: str
    student_id: Optional[str] = None
    alert_type: str
    description: Optional[str] = None
    confidence: Optional[float] = None
    status: str
    created_at: datetime

class AlertUpdateRequest(BaseModel):
    status: str  # New | Reviewed | Dismissed
