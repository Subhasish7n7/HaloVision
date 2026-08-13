from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SignupSchema(BaseModel):
    name: str
    email: str
    password: str


class LoginSchema(BaseModel):
    email: str
    password: str


class ProfileUpdateSchema(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None


class ChangePasswordSchema(BaseModel):
    current_password: str
    new_password: str


class UserPreferenceSchema(BaseModel):
    tts_speed: Optional[float] = 1
    default_mode: Optional[str] = "navigation"
    voice: Optional[str] = "default"
    theme: Optional[str] = "dark"


class SpeechSpeakSchema(BaseModel):
    speech_text: str

class SignupSchema(BaseModel):
    name: str
    email: str
    password: str

class LoginSchema(BaseModel):
    email: str
    password: str

class DetectionResponse(BaseModel):
    id: int
    label: str
    confidence: float
    distance: Optional[float] = None
    threat_level: int
    user_id: Optional[int] = None
    timestamp: datetime

    class Config:
        from_attributes = True

class SessionResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    active_mode: Optional[str] = None
    frames_processed: int
    start_time: datetime
    end_time: Optional[datetime] = None

    class Config:
        from_attributes = True

class AlertResponse(BaseModel):
    id: int
    type: str
    severity: int
    message: str
    object_label: Optional[str] = None
    user_id: Optional[int] = None
    timestamp: datetime

    class Config:
        from_attributes = True

class SearchQueryResponse(BaseModel):
    id: int
    query_text: str
    found: Optional[int] = None
    user_id: Optional[int] = None
    timestamp: datetime

    class Config:
        from_attributes = True

class UserPreferenceSchema(BaseModel):
    tts_speed: Optional[int] = 1
    default_mode: Optional[str] = "navigation"
    voice: Optional[str] = "default"
    theme: Optional[str] = "dark"

class VoiceCommandResponse(BaseModel):
    id: int
    command_text: str
    action: Optional[str] = None
    success: Optional[int] = None
    user_id: Optional[int] = None
    timestamp: datetime

    class Config:
        from_attributes = True