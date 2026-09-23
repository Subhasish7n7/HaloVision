# =============================================================================
# FILE: App/api/schemas.py
# ROLE: Pydantic schemas — request/response validation for API endpoints.
#
# WHAT THIS FILE DOES:
#   Defines Pydantic models that validate incoming request bodies
#   and structure outgoing responses. FastAPI uses these schemas
#   for automatic request validation and OpenAPI documentation.
#
# WHO USES THIS:
#   - main.py route handlers: use these for request body validation
#   - FastAPI auto-generates OpenAPI docs from these schemas
# =============================================================================

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# --- Auth Schemas ---

class SignupSchema(BaseModel):
    """Request body for POST /api/auth/signup"""
    name: str
    email: str
    password: str


class LoginSchema(BaseModel):
    """Request body for POST /api/auth/login"""
    email: str
    password: str


class ProfileUpdateSchema(BaseModel):
    """Request body for PUT /api/auth/profile"""
    name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    photo_url: Optional[str] = None


class ChangePasswordSchema(BaseModel):
    """Request body for PUT /api/auth/change-password"""
    current_password: str
    new_password: str


class UserPreferenceSchema(BaseModel):
    """Request body for POST /api/preferences"""
    tts_speed: Optional[float] = 1
    default_mode: Optional[str] = "navigation"
    voice: Optional[str] = "default"
    theme: Optional[str] = "dark"


class SpeechSpeakSchema(BaseModel):
    """Request body for POST /scene/speak"""
    speech_text: str


class ContactFormSchema(BaseModel):
    """Request body for POST /api/contact"""
    name: str
    email: str
    subject: Optional[str] = ""
    message: str


# --- Response Schemas ---

class DetectionResponse(BaseModel):
    """Response schema for detection data"""
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
    """Response schema for session data"""
    id: int
    user_id: Optional[int] = None
    active_mode: Optional[str] = None
    frames_processed: int
    start_time: datetime
    end_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class AlertResponse(BaseModel):
    """Response schema for alert data"""
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
    """Response schema for search query data"""
    id: int
    query_text: str
    found: Optional[int] = None
    user_id: Optional[int] = None
    timestamp: datetime

    class Config:
        from_attributes = True


class VoiceCommandResponse(BaseModel):
    """Response schema for voice command data"""
    id: int
    command_text: str
    action: Optional[str] = None
    success: Optional[int] = None
    user_id: Optional[int] = None
    timestamp: datetime

    class Config:
        from_attributes = True
