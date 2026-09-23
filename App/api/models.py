# =============================================================================
# FILE: App/api/models.py
# ROLE: ORM models — defines all database tables as Python classes.
#
# WHAT THIS FILE DOES:
#   Defines 12 SQLAlchemy ORM models that map to PostgreSQL tables.
#   Each model represents a table and defines its columns, relationships,
#   and constraints.
#
# TABLE GROUPS:
#   1. Core user data: User, Detection, Session, Alert, SearchQuery,
#      UserPreference, VoiceCommand
#   2. Enterprise admin: LoginAttempt, AdminActivity, FeatureFlag,
#      SystemSetting, Subscription
#
# KEY RELATIONSHIPS:
#   User → has many Detections, Sessions, Alerts, SearchQueries, etc.
#
# WHO USES THIS:
#   - main.py: creates tables with Base.metadata.create_all()
#   - All API routes: query these models for CRUD operations
#   - migrations.py: adds columns to existing tables
# =============================================================================

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from App.api.database import Base

class User(Base):
    """User account — the central entity for all data.
    Every other table has a user_id foreign key linking back to this."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    password = Column(String)  # bcrypt-hashed password

    # --- Enterprise RBAC / subscription fields (added via migration) ---
    role = Column(String, default="free", index=True)  # super_admin, admin, moderator, support, premium, free
    plan = Column(String, default="free")  # free | pro | pro_plus
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

    # Relationships — one user has many of each
    detections = relationship("Detection", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")
    search_queries = relationship("SearchQuery", back_populates="user", cascade="all, delete-orphan")
    preference = relationship("UserPreference", back_populates="user", uselist=False, cascade="all, delete-orphan")
    voice_commands = relationship("VoiceCommand", back_populates="user", cascade="all, delete-orphan")
    logins = relationship("LoginAttempt", back_populates="user", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")


class Detection(Base):
    """A single detection event — recorded when the vision pipeline finds an object."""
    __tablename__ = "detections"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String)           # Object class (e.g. "person", "car")
    confidence = Column(Float)       # Detection confidence (0-1)
    distance = Column(Float, nullable=True)  # Depth value
    threat_level = Column(Integer, default=0)  # 0-3
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="detections")

class Session(Base):
    """A usage session — tracks how long the user used the system."""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    active_mode = Column(String, nullable=True)  # navigation, search, etc.
    frames_processed = Column(Integer, default=0)
    start_time = Column(DateTime, server_default=func.now())
    end_time = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="sessions")

class Alert(Base):
    """A safety alert — triggered when a threat is detected."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String)            # Alert type (e.g. "threat", "collision")
    severity = Column(Integer, default=0)  # 0-3
    message = Column(String)         # Human-readable alert message
    object_label = Column(String, nullable=True)  # What triggered the alert
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="alerts")

class SearchQuery(Base):
    """A search query — when the user searches for a specific object."""
    __tablename__ = "search_queries"

    id = Column(Integer, primary_key=True, index=True)
    query_text = Column(String)      # What the user searched for
    found = Column(Integer, nullable=True)  # 1 if found, 0 if not
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="search_queries")

class UserPreference(Base):
    """User TTS/UI preferences — one row per user."""
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    tts_speed = Column(Integer, default=1)
    default_mode = Column(String, default="navigation")
    voice = Column(String, default="default")
    theme = Column(String, default="dark")

    user = relationship("User", back_populates="preference")

class VoiceCommand(Base):
    """A voice command — when the user speaks a command to the system."""
    __tablename__ = "voice_commands"

    id = Column(Integer, primary_key=True, index=True)
    command_text = Column(String)    # What the user said
    action = Column(String, nullable=True)  # What action was taken
    success = Column(Integer, nullable=True)  # 1 if successful
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="voice_commands")


# =========================
# ENTERPRISE ADMIN TABLES
# =========================

class LoginAttempt(Base):
    """Audit trail for login attempts — records every login attempt."""
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    email = Column(String, nullable=True)
    success = Column(Boolean, default=False)
    ip = Column(String, nullable=True)       # Client IP address
    user_agent = Column(String, nullable=True)  # Browser user agent
    timestamp = Column(DateTime, server_default=func.now(), index=True)

    user = relationship("User", back_populates="logins")


class AdminActivity(Base):
    """Audit log for admin actions — tracks all admin operations."""
    __tablename__ = "admin_activity"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    admin_email = Column(String, nullable=True)
    action = Column(String)          # e.g. "user.update", "settings.update"
    target = Column(String, nullable=True)  # What was affected
    detail = Column(Text, nullable=True)    # Additional details
    ip = Column(String, nullable=True)
    timestamp = Column(DateTime, server_default=func.now(), index=True)


class FeatureFlag(Base):
    """Runtime feature toggles — admins can enable/disable features without restart."""
    __tablename__ = "feature_flags"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)  # e.g. "show_tracking_ids"
    category = Column(String, default="general")    # e.g. "ui", "speech", "features"
    label = Column(String, nullable=True)           # Human-readable label
    enabled = Column(Boolean, default=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SystemSetting(Base):
    """Key-value configuration store — all runtime settings live here.
    Admins can change these at runtime without restarting the server."""
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True)  # e.g. "openai_api_key", "tts_speed"
    value = Column(Text, nullable=True)
    is_secret = Column(Boolean, default=False)  # Hidden in admin UI if True
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Subscription(Base):
    """Payment/subscription history — one row per payment event."""
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    plan = Column(String, default="free")
    status = Column(String, default="active")  # active | cancelled | expired | upgraded
    amount = Column(Float, default=0.0)
    currency = Column(String, default="USD")
    payment_method = Column(String, nullable=True)  # "razorpay", "simulated"
    payment_id = Column(String, nullable=True)      # Razorpay payment ID
    receipt = Column(String, nullable=True)         # Razorpay order ID
    started_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="subscriptions")

