from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from App.api.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    password = Column(String)

    # --- Enterprise RBAC / subscription fields (added via migration) ---
    role = Column(String, default="free", index=True)
    plan = Column(String, default="free")  # free | pro | business | enterprise
    is_active = Column(Boolean, default=True)
    is_banned = Column(Boolean, default=False)
    is_email_verified = Column(Boolean, default=False)
    plan_expires_at = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)

    # --- Extended profile fields (added via migration) ---
    phone = Column(String, nullable=True)
    address = Column(String, nullable=True)
    photo_url = Column(Text, nullable=True)

    detections = relationship("Detection", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")
    search_queries = relationship("SearchQuery", back_populates="user", cascade="all, delete-orphan")
    preference = relationship("UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")
    voice_commands = relationship("VoiceCommand", back_populates="user", cascade="all, delete-orphan")
    logins = relationship("LoginAttempt", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    persons = relationship("Person", back_populates="user", cascade="all, delete-orphan")
    meetups = relationship("Meetup", back_populates="user", cascade="all, delete-orphan")
    meetup_sessions = relationship("MeetupSession", back_populates="user", cascade="all, delete-orphan")
    meetup_settings = relationship("MeetupSetting", back_populates="user", uselist=False, cascade="all, delete-orphan")

class Detection(Base):
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String)
    confidence = Column(Float)
    distance = Column(Float, nullable=True)
    threat_level = Column(Integer, default=0)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="detections")

class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    active_mode = Column(String, nullable=True)
    frames_processed = Column(Integer, default=0)
    start_time = Column(DateTime, server_default=func.now())
    end_time = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="sessions")

class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String)
    severity = Column(Integer, default=0)
    message = Column(String)
    object_label = Column(String, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="alerts")

class SearchQuery(Base):
    __tablename__ = "search_queries"

    id = Column(Integer, primary_key=True, index=True)
    query_text = Column(String)
    found = Column(Integer, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="search_queries")

class UserPreference(Base):
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    tts_speed = Column(Integer, default=1)
    default_mode = Column(String, default="navigation")
    voice = Column(String, default="default")
    theme = Column(String, default="dark")

    user = relationship("User", back_populates="preference")

class VoiceCommand(Base):
    __tablename__ = "voice_commands"

    id = Column(Integer, primary_key=True, index=True)
    command_text = Column(String)
    action = Column(String, nullable=True)
    success = Column(Integer, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="voice_commands")


# =========================
# ENTERPRISE ADMIN TABLES
# =========================
class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    email = Column(String, nullable=True)
    success = Column(Boolean, default=False)
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    timestamp = Column(DateTime, server_default=func.now(), index=True)

    user = relationship("User", back_populates="logins")


class AdminActivity(Base):
    __tablename__ = "admin_activity"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    admin_email = Column(String, nullable=True)
    action = Column(String)  # user.update | user.delete | settings.update ...
    target = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    ip = Column(String, nullable=True)
    timestamp = Column(DateTime, server_default=func.now(), index=True)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    category = Column(String, default="general")
    label = Column(String, nullable=True)
    enabled = Column(Boolean, default=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)
    is_secret = Column(Boolean, default=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    plan = Column(String, default="free")
    status = Column(String, default="active")  # active | cancelled | expired | trial
    amount = Column(Float, default=0.0)
    currency = Column(String, default="USD")
    payment_method = Column(String, nullable=True)
    payment_id = Column(String, nullable=True)
    receipt = Column(String, nullable=True)
    started_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="subscriptions")


# =========================
# MEETUP MEMORY TABLES
#
# Phase 1: data model + workflow. Raw media lives on disk/object storage and
# is referenced via `StorageFile` / `recording_reference` — never embedded.
# Deletion is explicit and cascading (see App/api/meetup.py): deleting an
# event removes every derived row, including face embeddings.
# =========================
class Person(Base):
    __tablename__ = "meetup_persons"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String, nullable=False)
    face_embedding = Column(Text, nullable=True)   # JSON float vector
    profile_image = Column(String, nullable=True)  # storage reference
    birthday = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    source_meetup_id = Column(Integer, nullable=True)  # plain ref: created from a meetup
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="persons")


class Meetup(Base):
    __tablename__ = "meetups"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    person_id = Column(Integer, ForeignKey("meetup_persons.id"), nullable=True, index=True)
    started_at = Column(DateTime, server_default=func.now())
    ended_at = Column(DateTime, nullable=True)
    duration_sec = Column(Integer, nullable=True)
    # confirmed | temporary (auto-expires) | archived
    status = Column(String, default="confirmed", index=True)
    retention_until = Column(DateTime, nullable=True)  # temporary expiry
    transcript = Column(Text, nullable=True)  # denormalized full text copy
    recording_reference = Column(String, nullable=True)
    interaction_score = Column(Float, nullable=True)
    source = Column(String, default="manual")  # manual | auto
    user_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="meetups")
    person = relationship("Person", foreign_keys=[person_id])


class ConversationSegment(Base):
    __tablename__ = "meetup_conversation_segments"

    id = Column(Integer, primary_key=True, index=True)
    meetup_id = Column(Integer, ForeignKey("meetups.id"), index=True, nullable=False)
    speaker = Column(String, default="Person")
    timestamp_sec = Column(Float, nullable=True)  # offset inside the session
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    meetup = relationship("Meetup", foreign_keys=[meetup_id])


class MemoryFact(Base):
    __tablename__ = "meetup_memory_facts"

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("meetup_persons.id"), nullable=True, index=True)
    meetup_id = Column(Integer, ForeignKey("meetups.id"), nullable=True, index=True)
    key = Column(String, nullable=False)   # name | company | job | birthday | interests | notes ...
    value = Column(Text, nullable=False)
    status = Column(String, default="suggested")  # suggested | confirmed | user-edited
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    person = relationship("Person", foreign_keys=[person_id])


class StorageFile(Base):
    __tablename__ = "meetup_storage_files"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    meetup_id = Column(Integer, ForeignKey("meetups.id"), nullable=True, index=True)
    kind = Column(String, default="video")  # video | audio | image
    path = Column(String, nullable=False)   # local or object-storage reference
    mime = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class MeetupSession(Base):
    __tablename__ = "meetup_sessions"

    # Temporary rolling interaction buffer. Nothing here is permanent — a
    # session must be explicitly promoted (-> Meetup) or it expires.
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    person_id = Column(Integer, ForeignKey("meetup_persons.id"), nullable=True, index=True)
    status = Column(String, default="active")  # active | staged | expired
    started_at = Column(DateTime, server_default=func.now())
    last_active_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    expires_at = Column(DateTime, nullable=True)
    transcript_so_far = Column(Text, nullable=True)
    interaction_score = Column(Float, default=0.0)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="meetup_sessions")

    face_detections = relationship("MeetupFaceDetection", back_populates="session", cascade="all, delete-orphan")


class MeetupFaceDetection(Base):
    __tablename__ = "meetup_face_detections"

    # A face snapshot captured during a temporary meetup session. Belongs to
    # the session first — it only becomes a remembered person when the user
    # explicitly saves/names it (review stage). Deleting the session removes
    # every detection row AND its snapshot file on disk.
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("meetup_sessions.id"), index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    person_id = Column(Integer, ForeignKey("meetup_persons.id"), nullable=True, index=True)  # filled on save/recognize
    track_id = Column(String, nullable=True)       # client-side track id
    snapshot_path = Column(String, nullable=False) # local storage reference
    mime = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    confidence = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)
    first_seen_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    status = Column(String, default="temporary")   # temporary | ignored | saved
    created_at = Column(DateTime, server_default=func.now())

    session = relationship("MeetupSession", back_populates="face_detections")


class MeetupSetting(Base):
    __tablename__ = "meetup_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, index=True)
    recording = Column(Boolean, default=True)
    conversation_memory = Column(Boolean, default=True)
    face_memory = Column(Boolean, default=True)
    auto_detect = Column(Boolean, default=True)
    temp_buffer_sec = Column(Integer, default=20)
    temporary_retention_days = Column(Integer, default=1)
    saved_retention_days = Column(Integer, nullable=True)  # NULL = keep forever
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="meetup_settings")
