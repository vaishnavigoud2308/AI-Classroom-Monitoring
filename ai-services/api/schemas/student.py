from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class StudentResponse(BaseModel):
    id: str
    name: str
    roll_number: str
    email: Optional[str] = None
    face_image_url: Optional[str] = None
    created_at: datetime

class StudentCreateRequest(BaseModel):
    name: str
    roll_number: str
    email: Optional[str] = None
    # data URL or raw base64 JPEG/PNG from webcam capture
    face_image_base64: str
