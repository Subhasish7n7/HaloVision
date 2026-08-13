"""Lightweight idempotent migrations for the enterprise admin tables.

`create_all` cannot add columns to the existing `users` table, so we issue
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements on startup, then create
the new tables and seed defaults (super admin + feature flags).
"""
import logging

from sqlalchemy import text

from App.api.database import Base, engine
from App.api import models

logger = logging.getLogger(__name__)

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

_SUBSCRIPTION_COLUMNS = [
    ("payment_id", "VARCHAR"),
    ("receipt", "VARCHAR"),
]

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

_INITIAL_ADMIN = ("Halo Admin", "admin@halovision.local", "Admin@12345")


def run_migrations():
    with engine.begin() as conn:
        for col, ddl in _USER_COLUMNS:
            conn.execute(
                text(f'ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {ddl}')
            )
        for col, ddl in _SUBSCRIPTION_COLUMNS:
            conn.execute(
                text(f'ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS {col} {ddl}')
            )

    # Create any missing tables (idempotent).
    models.Base.metadata.create_all(bind=engine)

    # Seed default feature flags.
    try:
        _seed_flags()
        _seed_settings()
        _seed_admin()
    except Exception as e:
        logger.warning(f"Seeding skipped: {e}")

    logger.info("Admin migrations complete")


def _seed_flags(engine=engine):
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
    from passlib.context import CryptContext
    from App.api.database import SessionLocal
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.email == _INITIAL_ADMIN[1]).first()
        if not existing:
            pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
            db.add(models.User(
                name=_INITIAL_ADMIN[0],
                email=_INITIAL_ADMIN[1],
                password=pwd.hash(_INITIAL_ADMIN[2]),
                role="super_admin",
                plan="enterprise",
                is_active=True,
                is_email_verified=True,
            ))
            db.commit()
            logger.info("Seeded initial super admin")
    finally:
        db.close()