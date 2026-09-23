# =============================================================================
# FILE: App/api/migrations.py
# ROLE: Idempotent startup migrations — schema changes and data seeding.
#
# WHAT THIS FILE DOES:
#   Runs on every server startup to:
#   1. Add missing columns to existing tables (ALTER TABLE ADD COLUMN IF NOT EXISTS)
#   2. Create any new tables (idempotent create_all)
#   3. Seed default feature flags
#   4. Seed default system settings
#   5. Seed the initial super admin account
#
# WHY THIS EXISTS:
#   SQLAlchemy's create_all() can CREATE new tables but can't ADD columns
#   to existing tables. This module handles schema evolution by issuing
#   ALTER TABLE statements that are safe to run multiple times.
#
# WHO CALLS THIS:
#   main.py calls migrations.run_migrations() at startup (before the server
#   starts accepting requests).
#
# SEED DATA:
#   - Feature flags: UI toggles, speech settings, platform features
#   - System settings: LLM config, TTS config, pricing, payment keys
#   - Initial admin: admin@halovision.local / Admin@12345
# =============================================================================

"""Lightweight idempotent migrations for the enterprise admin tables.

`create_all` cannot add columns to the existing `users` table, so we issue
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements on startup, then create
the new tables and seed defaults (super admin + feature flags).
"""
import logging
import os

from sqlalchemy import text

from App.api.database import Base, engine
from App.api import models

logger = logging.getLogger(__name__)

# Columns to add to the existing users table (if missing)
_USER_COLUMNS = [
    ("role", "VARCHAR DEFAULT 'free'"),
    ("plan", "VARCHAR DEFAULT 'free'"),
    ("is_active", "BOOLEAN DEFAULT TRUE"),
    ("is_banned", "BOOLEAN DEFAULT FALSE"),
    ("is_email_verified", "BOOLEAN DEFAULT FALSE"),
    ("plan_expires_at", "TIMESTAMP"),
    ("last_login_at", "TIMESTAMP"),
    ("created_at", "TIMESTAMP DEFAULT NOW()"),
    ("phone", "VARCHAR"),
    ("address", "VARCHAR"),
    ("photo_url", "TEXT"),
]

# Columns to add to the existing subscriptions table (if missing)
_SUBSCRIPTION_COLUMNS = [
    ("payment_id", "VARCHAR"),
    ("receipt", "VARCHAR"),
]

# Default feature flags — seeded on first run
# (key, category, label, default_enabled)
_DEFAULT_FLAGS = [
    ("ai_search", "features", "AI Search", True),
    ("scene_description", "features", "Scene Description", True),
    ("ocr", "features", "OCR", True),
    ("navigation", "features", "Navigation", True),
    ("face_detection", "features", "Face Detection", True),
    ("depth", "features", "Depth Estimation", True),
    ("speech", "features", "Voice / TTS", True),
    ("cloud_sync", "platform", "Cloud Sync", True),
    ("notifications", "platform", "Notifications", True),
    ("analytics", "platform", "Analytics", True),
    ("tts_announcements", "speech", "TTS Detection Announcements", True),
    ("tts_priority", "speech", "TTS Priority", True),
    ("tts_duplicate_classes", "speech", "TTS Duplicate Classes", True),
    ("show_tracking_ids", "ui", "Show Tracking IDs", True),
    ("show_confidence", "ui", "Show Confidence", False),
    ("box_colors", "ui", "Per-ID Box Colors", True),
    ("show_hand_tracking", "ui", "Hand Tracking", True),
    ("show_finger_boxes", "ui", "Finger Boxes", True),
    ("show_finger_labels", "ui", "Finger Labels", True),
    ("show_finger_tips", "ui", "Fingertip Markers", True),
    ("show_gesture", "ui", "Gesture Chip", True),
    ("show_landmarks", "ui", "Hand Landmarks", False),
]

# Initial super admin credentials (created on first run only)
# Password must be provided via environment variable in production.
_INITIAL_ADMIN_NAME = os.getenv("ADMIN_NAME", "Halo Admin")
_INITIAL_ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@halovision.local")
_INITIAL_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


def run_migrations():
    """Run all idempotent migrations on startup.

    Flow:
        1. ALTER TABLE users ADD COLUMN IF NOT EXISTS (for each missing column)
        2. ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS
        3. CREATE TABLE IF NOT EXISTS (for all ORM models)
        4. Seed default feature flags
        5. Seed default system settings
        6. Seed initial super admin account
    """
    with engine.begin() as conn:
        # Add missing columns to users table
        for col, ddl in _USER_COLUMNS:
            conn.execute(
                text(f'ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {ddl}')
            )
        # Add missing columns to subscriptions table
        for col, ddl in _SUBSCRIPTION_COLUMNS:
            conn.execute(
                text(f'ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS {col} {ddl}')
            )

    # Create any missing tables (idempotent — safe to run multiple times)
    models.Base.metadata.create_all(bind=engine)

    # Seed default data
    try:
        _seed_flags()
        _seed_settings()
        _seed_admin()
    except Exception as e:
        logger.warning(f"Seeding skipped: {e}")

    logger.info("Admin migrations complete")


def _seed_flags(engine=engine):
    """Insert default feature flags (only if they don't already exist)."""
    from App.api.database import SessionLocal
    db = SessionLocal()
    try:
        existing = {f.key for f in db.query(models.FeatureFlag).all()}
        for key, category, label, default_enabled in _DEFAULT_FLAGS:
            if key not in existing:
                db.add(models.FeatureFlag(key=key, category=category, label=label, enabled=default_enabled))
        db.commit()
    finally:
        db.close()


def _seed_settings(engine=engine):
    """Insert default system settings (only if they don't already exist).
    These settings are admin-editable at runtime via the admin panel."""
    from App.api.database import SessionLocal
    db = SessionLocal()
    try:
        for key, default, secret in [
            ("upload_limit_mb", "25", False),
            ("rate_limit_per_minute", "120", False),
            ("yolo_confidence", "0.45", False),
            ("search_confidence", "0.25", False),
            ("smtp_host", "", False),
            ("smtp_port", "587", False),
            ("plan_pro_price", "5.99", False),
            ("plan_pro_plus_price", "14.99", False),
            ("payment_currency", "INR", False),
            ("razorpay_key_id", "", True),
            ("razorpay_key_secret", "", True),
            ("llm_enabled", "true", False),
            ("llm_provider", "openai", False),
            ("llm_model", "gpt-4o-mini", False),
            ("openai_api_key", "", True),
            ("gemini_api_key", "", True),
            ("tts_cooldown_sec", "60", False),
            ("tts_queue_max", "5", False),
            ("tts_grace_sec", "5", False),
            ("tts_id_expiry_sec", "120", False),
            ("tts_speed", "1.0", False),
            ("tts_voice", "en-US-AriaNeural", False),
            ("inference_backend", "auto", False),
            ("depth_quality", "fast", False),
            ("depth_refresh_ms", "600", False),
            ("yolo_imgsz", "480", False),
        ]:
            exists = db.query(models.SystemSetting).filter_by(key=key).first()
            if not exists:
                db.add(models.SystemSetting(key=key, value=default, is_secret=secret))
        db.commit()
    finally:
        db.close()


def _seed_admin():
    """Create the initial super admin account (only if it doesn't exist).
    Credentials come from environment variables: ADMIN_EMAIL / ADMIN_PASSWORD."""
    from passlib.context import CryptContext
    from App.api.database import SessionLocal
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.email == _INITIAL_ADMIN_EMAIL).first()
        if not existing:
            if not _INITIAL_ADMIN_PASSWORD:
                logger.warning(
                    "ADMIN_PASSWORD not set — skipping initial admin seed. "
                    "Set ADMIN_PASSWORD env var and restart to create the admin account."
                )
                return
            pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
            db.add(models.User(
                name=_INITIAL_ADMIN_NAME,
                email=_INITIAL_ADMIN_EMAIL,
                password=pwd.hash(_INITIAL_ADMIN_PASSWORD),
                role="super_admin",
                plan="enterprise",
                is_active=True,
                is_email_verified=True,
            ))
            db.commit()
            logger.info("Seeded initial super admin")
    finally:
        db.close()
