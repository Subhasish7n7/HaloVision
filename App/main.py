# =============================================================================
# FILE: App/main.py
# ROLE: Core application file — FastAPI app definition, all routes, and
#       system initialization. This is the central hub that wires together
#       every layer of HaloVision.
#
# WHAT THIS FILE DOES:
#   1. Creates the FastAPI application
#   2. Configures CORS, static files, database
#   3. Defines REST API routes (auth, user profile, detections, etc.)
#   4. Initializes the AI pipeline (tracker, depth, perception, event bus)
#   5. Wires up the event-driven processing chain at startup
#   6. Defines WebSocket endpoints for real-time camera streaming
#
# ARCHITECTURE:
#   This file sits at the intersection of ALL layers:
#     - Imports from App/api/ (database, models, auth, schemas)
#     - Imports from App/core/ (event bus, reasoning, rule engine, speech)
#     - Imports from App/Perception/ (tracker, depth, perception system)
#     - Imports from App/api/webRTC.py (WebSocket/WebRTC transport)
#
# STARTUP WIRING (the "glue" that connects the pipeline):
#   EventBus.subscribe("PERCEPTION_FRAME_READY") → send_detections (WebSocket broadcast)
#   EventBus.subscribe("PERCEPTION_FRAME_READY") → ReasoningLayer.handle_event
#   EventBus.subscribe("FRAME_ANALYSIS_READY")   → RuleEngine.handle_event
#
# END-TO-END FLOW:
#   Browser camera → WebSocket/WebRTC → decoded frame
#       → PerceptionSystem.process_frame() → SystemEvent("PERCEPTION_FRAME_READY")
#           → EventBus fans out to 3 handlers:
#               1. send_detections() → broadcasts JSON to all clients
#               2. ReasoningLayer    → evaluates threats, builds scene graph
#                   → publishes "FRAME_ANALYSIS_READY"
#                       → RuleEngine → generates SpeechIntent
#                           → publishes "SPEECH_INTENT_CREATED"
#                               → SpeechScheduler → TTSEngine → audio playback
# =============================================================================

import os
import io
import asyncio
import time as time_mod
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env BEFORE anything else.
# This sets DATABASE_URL, CORS_ORIGINS, SECRET_KEY, etc.
load_dotenv()

from fastapi import FastAPI, WebSocket, Depends, HTTPException, Header, UploadFile, File, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import logging
import numpy as np
import cv2

# ---- Database & ORM ----
# SessionLocal is a SQLAlchemy session factory; engine is the DB connection.
from App.api.database import SessionLocal, engine
from App.api import models, schemas, auth

# ---- Sub-routers (mounted on the app below) ----
from App.api.admin import admin_router
from App.api.billing import billing_router
from App.api import migrations

# ---- Core Layer: Event bus, reasoning, rule engine, speech ----
from App.core.event_bus import AsyncEventBus
from App.core.reasoning_layer import ReasoningLayer
from App.core.safety import DEPTH_VERY_CLOSE, DEPTH_NEAR
from App.core.rule_engine import RuleEngine
from App.core.speech_scheduler import SpeechScheduler
import edge_tts

# ---- Perception Layer: YOLO tracking, depth estimation ----
from App.Perception.perception_system import PerceptionSystem
from App.Perception.tracker import ObjectTracker
from App.Perception.depth_updater import DepthUpdater
from App.Perception.depth_estimator import create_depth_estimator, _DEFAULT_ONNX_PATH
from App.Perception.inference_backend import resolve_backend, describe as describe_backend

# ---- Transport Layer: WebSocket/WebRTC frame ingress + outbound broadcast ----
from App.api.webRTC import (
    register_client,
    receive_frames,
    send_detections,
    rtc_endpoint,
)

# =============================================================================
# LOGGING
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# =============================================================================
# FASTAPI APP CREATION
# =============================================================================
app = FastAPI(title="HaloVision API", version="1.0.0")

# ---- Static file serving for media (face snapshots, recordings) ----
# The media directory lives on disk; the DB stores references (paths).
_media_dir = Path(__file__).resolve().parent.parent / "media"
_media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=_media_dir), name="media")

# ---- Mount sub-routers for admin and billing features ----
app.include_router(admin_router)
app.include_router(billing_router)

# ---- CORS configuration ----
# Allows the frontend (Vite dev server on port 5173, etc.) to make requests.
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================
# Creates all tables if they don't exist, then runs idempotent migrations
# to add missing columns, seed default feature flags, system settings,
# and the initial super admin account.
try:
    logger.info("Initializing database...")
    models.Base.metadata.create_all(bind=engine)
    migrations.run_migrations()
    logger.info("Database ready")
except Exception as e:
    logger.warning(f"Database unavailable: {e}. The app will start, but DB endpoints will fail.")

# =============================================================================
# DEPENDENCY INJECTORS
# =============================================================================

def get_db():
    """FastAPI dependency: yields a SQLAlchemy session, closes it after the request.
    Used by route handlers that need database access."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(authorization: str = Header(None)):
    """FastAPI dependency: extracts and verifies the JWT token from the
    Authorization header. Returns the decoded payload (contains user_id).
    Raises 401 if the token is missing, malformed, or expired.

    Flow:
        Request header "Authorization: Bearer <token>"
            → extract token string
            → auth.verify_token() decodes JWT (HS256)
            → returns payload dict with "user_id" key
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    payload = auth.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload

# =============================================================================
# AUTH ROUTES
# =============================================================================

@app.post("/api/auth/signup")
def signup(user: schemas.SignupSchema, db: Session = Depends(get_db)):
    """Register a new user account.
    Flow:
        Frontend sends {name, email, password}
            → check if email already exists
            → hash password with bcrypt
            → create User row in database
            → return success message
    """
    try:
        logger.info("Signup request received")

        existing = db.query(models.User).filter(models.User.email == user.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already exists")

        # Hash the plaintext password before storing (never store raw passwords)
        hashed = auth.hash_password(user.password)
        new_user = models.User(name=user.name, email=user.email, password=hashed)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        logger.info("User created successfully")
        return {"message": "User created"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Signup error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/api/auth/login")
def login(user: schemas.LoginSchema, request: Request, db: Session = Depends(get_db)):
    """Authenticate a user and return a JWT token.
    Flow:
        Frontend sends {email, password}
            → look up user by email
            → verify password against bcrypt hash
            → check if user is banned
            → create JWT token (1-hour expiry)
            → log the login attempt (IP, user agent)
            → return token + user profile
    The token is then used in the Authorization header for all subsequent requests.
    """
    try:
        logger.info("Login request received")

        existing = db.query(models.User).filter(models.User.email == user.email).first()
        if not existing:
            raise HTTPException(status_code=400, detail="User not found")

        if not auth.verify_password(user.password, existing.password):
            raise HTTPException(status_code=400, detail="Invalid password")

        if existing.is_banned:
            raise HTTPException(status_code=403, detail="Account banned")

        # Create JWT token — payload contains user_id, used by get_current_user()
        token = auth.create_token({"user_id": existing.id})
        existing.last_login_at = datetime.now(timezone.utc)
        db.add(existing)
        # Audit trail: record every login attempt for security
        db.add(models.LoginAttempt(
            user_id=existing.id,
            email=existing.email,
            success=True,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent")[:200] if request.headers.get("user-agent") else None,
        ))
        db.commit()
        logger.info("Login successful")
        return {
            "token": token,
            "user": {
                "id": existing.id,
                "name": existing.name,
                "email": existing.email,
                "role": existing.role or "free",
                "plan": existing.plan or "free",
                "is_active": bool(existing.is_active),
                "is_banned": bool(existing.is_banned),
                "phone": existing.phone,
                "address": existing.address,
                "photo_url": existing.photo_url,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/api/auth/me")
def me(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return the current user's profile.
    Requires a valid JWT token. Uses the user_id from the token
    to look up the full profile from the database."""
    profile = db.query(models.User).filter(models.User.id == user.get("user_id")).first()
    if not profile:
        raise HTTPException(status_code=401, detail="User not found")
    return {
        "id": profile.id,
        "name": profile.name,
        "email": profile.email,
        "role": profile.role or "free",
        "plan": profile.plan or "free",
        "is_active": bool(profile.is_active),
        "is_banned": bool(profile.is_banned),
        "phone": profile.phone,
        "address": profile.address,
        "photo_url": profile.photo_url,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }

@app.put("/api/auth/profile")
def update_profile(body: schemas.ProfileUpdateSchema, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Update the current user's profile fields (name, phone, address, photo)."""
    profile = db.query(models.User).filter(models.User.id == user.get("user_id")).first()
    if not profile:
        raise HTTPException(status_code=401, detail="User not found")
    if body.name is not None:
        profile.name = body.name.strip() or profile.name
    if body.phone is not None:
        profile.phone = body.phone.strip() or None
    if body.address is not None:
        profile.address = body.address.strip() or None
    if body.photo_url is not None:
        profile.photo_url = body.photo_url.strip() or None
    db.commit()
    db.refresh(profile)
    return {
        "id": profile.id,
        "name": profile.name,
        "email": profile.email,
        "role": profile.role or "free",
        "plan": profile.plan or "free",
        "is_active": bool(profile.is_active),
        "is_banned": bool(profile.is_banned),
        "phone": profile.phone,
        "address": profile.address,
        "photo_url": profile.photo_url,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }

@app.put("/api/auth/change-password")
def change_password(body: schemas.ChangePasswordSchema, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Change the current user's password after verifying the old one."""
    profile = db.query(models.User).filter(models.User.id == user.get("user_id")).first()
    if not profile:
        raise HTTPException(status_code=401, detail="User not found")
    if not auth.verify_password(body.current_password, profile.password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters")
    profile.password = auth.hash_password(body.new_password)
    db.commit()
    return {"message": "Password changed successfully"}

# =============================================================================
# USER DATA ROUTES (detections, sessions, alerts, preferences)
# =============================================================================
# These routes return historical data stored in the database.
# The vision pipeline writes detection data here; these routes read it back.

@app.get("/api/detections")
def get_detections(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Return the user's detection history (most recent 100)."""
    user_id = user.get("user_id")
    detections = db.query(models.Detection).filter(
        models.Detection.user_id == user_id
    ).order_by(models.Detection.timestamp.desc()).limit(100).all()
    return detections

@app.get("/api/sessions")
def get_sessions(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Return the user's usage sessions (most recent 50)."""
    user_id = user.get("user_id")
    sessions = db.query(models.Session).filter(
        models.Session.user_id == user_id
    ).order_by(models.Session.start_time.desc()).limit(50).all()
    return sessions

@app.get("/api/alerts")
def get_alerts(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Return the user's safety alerts (most recent 100)."""
    user_id = user.get("user_id")
    alerts = db.query(models.Alert).filter(
        models.Alert.user_id == user_id
    ).order_by(models.Alert.timestamp.desc()).limit(100).all()
    return alerts

@app.get("/api/search-queries")
def get_search_queries(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Return the user's object search history."""
    user_id = user.get("user_id")
    queries = db.query(models.SearchQuery).filter(
        models.SearchQuery.user_id == user_id
    ).order_by(models.SearchQuery.timestamp.desc()).limit(100).all()
    return queries

@app.get("/api/preferences")
def get_preferences(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Return user TTS/UI preferences, or defaults if none saved."""
    user_id = user.get("user_id")
    prefs = db.query(models.UserPreference).filter(
        models.UserPreference.user_id == user_id
    ).first()
    if not prefs:
        return {"tts_speed": 1, "default_mode": "navigation", "voice": "default", "theme": "dark"}
    return prefs

@app.post("/api/preferences")
def save_preferences(prefs: schemas.UserPreferenceSchema, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Create or update user TTS/UI preferences."""
    user_id = user.get("user_id")
    existing = db.query(models.UserPreference).filter(
        models.UserPreference.user_id == user_id
    ).first()
    if existing:
        existing.tts_speed = prefs.tts_speed
        existing.default_mode = prefs.default_mode
        existing.voice = prefs.voice
        existing.theme = prefs.theme
    else:
        new_prefs = models.UserPreference(user_id=user_id, **prefs.model_dump())
        db.add(new_prefs)
    db.commit()
    return {"message": "Preferences saved"}

@app.get("/api/voice-commands")
def get_voice_commands(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Return the user's voice command history."""
    user_id = user.get("user_id")
    commands = db.query(models.VoiceCommand).filter(
        models.VoiceCommand.user_id == user_id
    ).order_by(models.VoiceCommand.timestamp.desc()).limit(100).all()
    return commands

@app.get("/health")
def health_check():
    """Simple health check endpoint — returns ok if the server is running."""
    return {"status": "ok"}


@app.post("/api/contact")
def contact_form(body: schemas.ContactFormSchema):
    """Handle contact form submissions.
    Logs the message and returns success. In production, this would
    send an email or store in a database."""
    logger.info(f"[CONTACT] From: {body.name} <{body.email}> | Subject: {body.subject}")
    logger.info(f"[CONTACT] Message: {body.message[:200]}")
    return {"message": "Message received. We'll get back to you soon."}


@app.get("/api/dashboard/stats")
def dashboard_stats(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    """Return real-time counts of the authenticated user's data.

    Uses database COUNT queries instead of fetching full lists.
    Returns actual totals regardless of how many records exist.
    """
    user_id = user.get("user_id")

    detections = db.query(models.Detection).filter(
        models.Detection.user_id == user_id
    ).count()

    sessions = db.query(models.Session).filter(
        models.Session.user_id == user_id
    ).count()

    alerts = db.query(models.Alert).filter(
        models.Alert.user_id == user_id
    ).count()

    searches = db.query(models.SearchQuery).filter(
        models.SearchQuery.user_id == user_id
    ).count()

    return {
        "detections": detections,
        "sessions": sessions,
        "alerts": alerts,
        "searches": searches,
    }


@app.get("/api/ui-config")
def ui_config(db: Session = Depends(get_db)):
    """Public UI configuration toggles (no auth needed).
    Drives the detection overlay rendering on the frontend.
    Reads from the feature_flags table in the database,
    allowing admins to toggle UI elements without restarting."""
    keys = (
        "show_tracking_ids",
        "show_confidence",
        "box_colors",
        "show_hand_tracking",
        "show_finger_boxes",
        "show_finger_labels",
        "show_finger_tips",
        "show_gesture",
        "show_landmarks",
    )
    flags = {
        f.key: f.enabled
        for f in db.query(models.FeatureFlag)
        .filter(models.FeatureFlag.key.in_(keys))
        .all()
    }
    return {
        "show_tracking_ids": flags.get("show_tracking_ids", True),
        "show_confidence": flags.get("show_confidence", False),
        "box_colors": flags.get("box_colors", True),
        "show_hand_tracking": flags.get("show_hand_tracking", True),
        "show_finger_boxes": flags.get("show_finger_boxes", True),
        "show_finger_labels": flags.get("show_finger_labels", True),
        "show_finger_tips": flags.get("show_finger_tips", True),
        "show_gesture": flags.get("show_gesture", True),
        "show_landmarks": flags.get("show_landmarks", False),
    }


# =============================================================================
# SCENE DESCRIPTION (SINGLE CAPTURE + LLM)
# =============================================================================
# This section handles one-shot image analysis (not the live stream).
# The user uploads a photo, the system processes it through the perception
# pipeline, and returns a description. Paid users get LLM-enhanced descriptions.

# Maps YOLO class names to human-readable names for the scene description
SCENE_NAMES = {
    "person": "person",
    "bicycle": "bicycle",
    "car": "car",
    "motorcycle": "motorcycle",
    "airplane": "airplane",
    "bus": "bus",
    "train": "train",
    "truck": "truck",
    "boat": "boat",
    "traffic light": "traffic light",
    "stop sign": "stop sign",
    "backpack": "backpack",
    "umbrella": "umbrella",
    "handbag": "handbag",
    "tie": "tie",
    "suitcase": "suitcase",
    "sports ball": "ball",
    "kite": "kite",
    "book": "book",
    "laptop": "laptop",
    "cell phone": "cell phone",
    "bottle": "bottle",
    "cup": "cup",
    "chair": "chair",
    "couch": "couch",
    "dining table": "dining table",
    "tv": "tv",
}
_TTS_VOICE = "en-US-AriaNeural"


def _describe_scene(objects):
    """Build a natural-language scene description from detected objects.
    Called by the /scene/analyze endpoint.

    Input:  list of ObjectData from the perception pipeline
    Output: (description, speech_text) tuple — description is for display,
            speech_text is for text-to-speech.

    Flow:
        objects from PerceptionSystem → group by class → rank by count/confidence
            → build phrases like "a person on your left, nearby"
            → detect scene type (indoor/outdoor) based on vehicle presence
            → return human-readable description
    """
    if not objects:
        desc = (
            "I don't see any clearly recognisable objects in this scene. "
            "The frame appears to be empty or low-light."
        )
        return desc, (
            "I don't see any recognisable objects in this frame. "
            "You may want to point towards something and try again."
        )

    # Group detected objects by their class name
    by_class = {}
    for obj in objects:
        name = SCENE_NAMES.get(obj.class_name.lower(), obj.class_name)
        by_class.setdefault(name, []).append(obj)

    # Rank classes by count (most objects first), then by highest confidence
    ranked = sorted(
        by_class.items(),
        key=lambda kv: (-len(kv[1]), -max(o.confidence for o in kv[1])),
    )

    # Build descriptive phrases for the top 3 object classes
    parts = []
    for name, objs in ranked[:3]:
        count = len(objs)
        sample = max(objs, key=lambda o: o.confidence)
        # Determine left/right position based on horizontal offset
        side = ""
        if sample.horizontal_offset_norm is not None:
            if sample.horizontal_offset_norm < -0.25:
                side = " on your left"
            elif sample.horizontal_offset_norm > 0.25:
                side = " on your right"

        # Determine distance description from depth value
        range_desc = ""
        if sample.depth_norm and sample.depth_norm > 0:
            if sample.depth_norm >= DEPTH_VERY_CLOSE:
                range_desc = " very close"
            elif sample.depth_norm >= DEPTH_NEAR:
                range_desc = " nearby"
            else:
                range_desc = " further away"

        if count > 1:
            parts.append(f"{count} {name}s{side}{range_desc}")
        else:
            parts.append(f"a {name}{side}{range_desc}")

    # Combine parts into a single description
    if len(parts) == 1:
        detail = parts[0]
    elif len(parts) == 2:
        detail = f"{parts[0]} and {parts[1]}"
    else:
        detail = f"{parts[0]}, {parts[1]}, and {parts[2]}"

    total = sum(len(v) for v in by_class.values())
    human = sum(len(v) for k, v in by_class.items() if "person" in k)

    # Infer scene type from detected object classes
    scene_type = "an indoor environment"
    vehicle_like = any(k in by_class for k in ("car", "bus", "truck", "motorcycle", "train", "bicycle", "boat"))
    if vehicle_like:
        scene_type = "an outdoor environment"

    desc = (
        f"I see {detail}. "
        f"There {'is' if total == 1 else 'are'} {total} object{'s' if total != 1 else ''} in view "
        f"and the scene looks like {scene_type}."
    )

    speech = (
        f"{detail.capitalize()}. "
        f"This appears to be {scene_type}."
    )
    return desc, speech


@app.post("/scene/analyze")
async def scene_analyze(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Analyze a single uploaded image — runs it through the full perception
    pipeline and returns a scene description.

    Flow:
        1. Frontend uploads an image file
        2. Decode bytes → OpenCV frame (numpy array)
        3. Run through PerceptionSystem.process_frame() (YOLO + depth)
        4. Extract detected objects from the event
        5. Build a rule-based description from objects
        6. If user is on a paid plan AND an OpenAI key is configured,
           enhance the description with LLM (GPT-4o-mini)
        7. Return JSON with description, speech text, objects, and metadata

    The response includes:
        - description: full text description for display
        - speech_text: shorter version for TTS
        - objects: list of detected objects with labels, confidence, bboxes
        - scene: frame metadata (frame_id, object count, processing time)
    """
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Read the uploaded file bytes and decode to OpenCV format
    raw = await file.read()
    try:
        arr = np.frombuffer(raw, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Could not decode uploaded image")

    if frame is None or frame.size == 0:
        raise HTTPException(status_code=400, detail="Could not decode uploaded image")

    # Clear any active search target so detection uses the normal confidence threshold
    import App.api.webRTC as ws_mod
    ws_mod.SEARCH_TARGET = None

    # Run the perception pipeline on this single frame
    # asyncio.to_thread runs the CPU-bound YOLO+depth work in a thread pool
    start = time_mod.time()
    try:
        event = await asyncio.to_thread(perception.process_frame, frame)
    except Exception as e:
        logger.error(f"Scene analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Scene analysis failed")

    # Extract objects from the perception event
    objects = list(event.payload.active_objects.values())
    logger.info(f"[SCENE] Perception found {len(objects)} objects")
    for o in objects:
        logger.info(f"[SCENE]   - {o.class_name} conf={o.confidence:.2f} depth={o.depth_norm:.2f} h_off={o.horizontal_offset_norm:.2f}")

    description, speech_text = _describe_scene(objects)
    logger.info(f"[SCENE] Rule-based description: {description[:120]}...")

    # Enhance with LLM for paid users (Pro/Pro+ plans)
    # Falls back to rule-based text on any failure
    db = SessionLocal()
    try:
        urow = db.query(models.User).filter(models.User.id == user.get("user_id")).first()
        if urow:
            from App.core.llm import build_scene_description
            logger.info(f"[SCENE] User plan: {getattr(urow, 'plan', 'free')}")
            # Run the blocking LLM HTTP call in a thread pool to avoid blocking the event loop
            description, _used_llm = await asyncio.to_thread(
                build_scene_description,
                db, urow, frame, description,
                objects=[
                    {"label": o.class_name, "confidence": round(float(o.confidence), 2)}
                    for o in objects
                ],
            )
            logger.info(f"[SCENE] LLM used: {_used_llm}, description type: {type(description).__name__}")
            if _used_llm and description:
                speech_text = description
        else:
            logger.warning(f"[SCENE] User {user.get('user_id')} not found in DB")
    finally:
        db.close()

    logger.info(f"[SCENE] Final description: {str(description)[:150]}")
    logger.info(f"[SCENE] Final speech_text: {str(speech_text)[:150]}")

    return {
        "description": description,
        "speech_text": speech_text,
        "objects": [
            {
                "id": obj.object_id,
                "track_id": obj.track_id,
                "label": obj.class_name,
                "confidence": round(float(obj.confidence), 2),
                "bbox": [int(v) for v in obj.bbox],
            }
            for obj in objects
        ],
        "scene": {
            "frame_id": event.payload.frame_id,
            "object_count": len(objects),
            "analysis_ms": round((time_mod.perf_counter() - start) * 1000),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/scene/speak")
async def scene_speak(
    payload: schemas.SpeechSpeakSchema,
    user: dict = Depends(get_current_user),
):
    """Convert text to speech audio and return the MP3 bytes.
    Uses Microsoft Edge TTS (free, cloud-based neural voices).
    The frontend plays this audio when the user requests scene description."""

    text = (payload.speech_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="speech_text is required")

    try:
        # Stream TTS audio chunks and collect into a buffer
        communicate = edge_tts.Communicate(text=text, voice=_TTS_VOICE)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}")
        raise HTTPException(status_code=500, detail="Speech synthesis failed")

    buf.seek(0)
    return Response(content=buf.read(), media_type="audio/mpeg")

# =============================================================================
# INFERENCE PIPELINE INITIALIZATION
# =============================================================================
# This section creates the global AI pipeline objects that process every frame.
# These are created ONCE at module load time and reused for every connection.

def _vision_settings():
    """Read vision/inference settings from the database.
    Admins can change these at runtime without restarting.
    Falls back to hardcoded defaults if the DB is unavailable."""
    out = {"backend": "auto", "quality": "fast", "imgsz": 480, "refresh_ms": 600}
    try:
        db = SessionLocal()
        try:
            rows = {r.key: r.value for r in db.query(models.SystemSetting).all()}
            out["backend"] = rows.get("inference_backend", "auto")
            out["quality"] = rows.get("depth_quality", "fast")
            out["imgsz"] = int(float(rows.get("yolo_imgsz", "480") or 480))
            out["refresh_ms"] = int(float(rows.get("depth_refresh_ms", "600") or 600))
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Vision settings unavailable ({e}) - using defaults")
    return out


# --- Resolve the best inference backend (TensorRT > OpenVINO > ONNX > PyTorch) ---
_vs = _vision_settings()
INFERENCE_BACKEND = resolve_backend(_vs["backend"])
logger.info(f"[Inference] active backend: {INFERENCE_BACKEND} ({describe_backend(INFERENCE_BACKEND)})")

# --- Create the global pipeline objects ---
# These are imported into routes and WebSocket handlers below.

bus = AsyncEventBus()                    # Pub/sub event bus connecting all layers
tracker = ObjectTracker(imgsz=_vs["imgsz"])  # YOLOv8 + ByteTrack object detector/tracker
depth_model = create_depth_estimator(INFERENCE_BACKEND, _vs["quality"], _DEFAULT_ONNX_PATH())  # MiDaS depth
depth_provider = DepthUpdater(depth_model, refresh_sec=_vs["refresh_ms"] / 1000.0)  # Async depth runner
perception = PerceptionSystem(tracker=tracker, depth_provider=depth_provider)  # Main frame processor

# =============================================================================
# STARTUP EVENT — wires up the event-driven pipeline
# =============================================================================
@app.on_event("startup")
async def startup():
    """Called once when the FastAPI server starts.
    This is where the entire event-driven pipeline is wired together.

    Flow:
        1. Create core components (ReasoningLayer, RuleEngine, SpeechScheduler)
        2. Subscribe handlers to events on the EventBus
        3. Start background tasks (speech scheduler, depth updater)
        4. The system is now ready to process camera frames

    Event subscriptions:
        "PERCEPTION_FRAME_READY" → send_detections      (broadcast to WebSocket clients)
        "PERCEPTION_FRAME_READY" → ReasoningLayer        (threat evaluation, scene graph)
        "FRAME_ANALYSIS_READY"   → RuleEngine            (speech intent generation)
        "SPEECH_INTENT_CREATED"  → SpeechScheduler       (priority queue → Azure TTS)
    """
    logger.info("Starting AI system...")

    # Create core components — they share the event bus
    reasoning = ReasoningLayer(bus)
    rule_engine = RuleEngine(bus)
    scheduler = SpeechScheduler(bus, cooldown_sec=0.1)

    # Wire up event handlers — each subscribes to a specific event type
    # When PerceptionSystem publishes "PERCEPTION_FRAME_READY", all handlers run concurrently
    await bus.subscribe("PERCEPTION_FRAME_READY", send_detections)
    await bus.subscribe("PERCEPTION_FRAME_READY", reasoning.handle_event)
    await bus.subscribe("FRAME_ANALYSIS_READY", rule_engine.handle_event)
    await bus.subscribe("USER_COMMAND_RECEIVED", rule_engine.handle_event)
    await bus.subscribe("HAND_GESTURE_DETECTED", rule_engine.handle_event)

    # Start background async tasks
    await scheduler.start()      # SpeechScheduler._run_loop() — processes speech queue
    await depth_provider.start() # DepthUpdater._run() — runs depth inference on its own cadence
    logger.info("System ready")

# =============================================================================
# WEBSOCKET ENDPOINTS — real-time camera streaming
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = None):
    """Classic JPEG-over-WebSocket transport (fallback for browsers without WebRTC).
    Flow:
        1. Browser connects and sends binary JPEG frames
        2. register_client() adds to the shared client list
        3. receive_frames() runs two concurrent tasks:
           - receiver(): reads incoming frames + JSON messages (mode/search)
           - processor(): decodes JPEG → runs perception → publishes to EventBus
        4. EventBus handlers broadcast detections + speech to all clients

    Authentication: JWT token is required via query parameter ?token=<jwt>.
    """
    # Authenticate via query parameter (WebSocket can't use headers easily)
    if not token:
        await ws.close(code=4001, reason="Missing authentication token")
        return
    payload = auth.verify_token(token)
    if not payload:
        await ws.close(code=4001, reason="Invalid or expired token")
        return
    user_id = payload.get("user_id")
    if not user_id:
        await ws.close(code=4001, reason="Invalid token payload")
        return

    logger.info(f"WebSocket connection request (user_id={user_id})")
    await register_client(ws)
    await receive_frames(ws, perception, bus)

@app.websocket("/rtc")
async def rtc_ws_endpoint(ws: WebSocket, token: str = None):
    """WebRTC signaling endpoint — lower latency than JPEG WebSocket.
    Flow:
        1. Browser connects for WebRTC signaling (offer/answer/ICE exchange)
        2. rtc_endpoint() handles the signaling protocol
        3. Once connected, the browser streams raw video (VP8/H264 RTP)
        4. Server decodes frames and runs the same perception pipeline
        5. Results broadcast to all clients (same as /ws path)

    Authentication: JWT token is required via query parameter ?token=<jwt>.
    """
    if not token:
        await ws.close(code=4001, reason="Missing authentication token")
        return
    payload = auth.verify_token(token)
    if not payload:
        await ws.close(code=4001, reason="Invalid or expired token")
        return
    user_id = payload.get("user_id")
    if not user_id:
        await ws.close(code=4001, reason="Invalid token payload")
        return

    logger.info(f"WebRTC signaling connection request (user_id={user_id})")
    await rtc_endpoint(ws, perception, bus)
