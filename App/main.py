import os
import io
import asyncio
import time as time_mod
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, WebSocket, Depends, HTTPException, Header, UploadFile, File, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import logging
import numpy as np
import cv2
import edge_tts

from App.api.database import SessionLocal, engine
from App.api import models, schemas, auth
from App.api.admin import admin_router
from App.api.billing import billing_router
from App.api import migrations

from App.core.event_bus import AsyncEventBus
from App.core.reasoning_layer import ReasoningLayer
from App.core.safety import DEPTH_VERY_CLOSE, DEPTH_NEAR
from App.core.rule_engine import RuleEngine
from App.core.speech_scheduler import SpeechScheduler
from App.core.detection_tts import DetectionTTSAnnouncer

from App.Perception.perception_system import PerceptionSystem
from App.Perception.tracker import ObjectTracker
from App.Perception.depth_updater import DepthUpdater
from App.Perception.depth_estimator import create_depth_estimator, _DEFAULT_ONNX_PATH
from App.Perception.inference_backend import resolve_backend, describe as describe_backend

from App.api.websocket import (
    register_client,
    receive_frames,
    send_detections,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="HaloVision API", version="1.0.0")

app.include_router(admin_router)
app.include_router(billing_router)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    logger.info("Initializing database...")
    models.Base.metadata.create_all(bind=engine)
    migrations.run_migrations()
    logger.info("Database ready")
except Exception as e:
    logger.warning(f"Database unavailable: {e}. The app will start, but DB endpoints will fail.")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    payload = auth.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload

@app.post("/api/auth/signup")
def signup(user: schemas.SignupSchema, db: Session = Depends(get_db)):
    try:
        logger.info("Signup request received")

        existing = db.query(models.User).filter(models.User.email == user.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already exists")

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
    try:
        logger.info("Login request received")

        existing = db.query(models.User).filter(models.User.email == user.email).first()
        if not existing:
            raise HTTPException(status_code=400, detail="User not found")

        if not auth.verify_password(user.password, existing.password):
            raise HTTPException(status_code=400, detail="Invalid password")

        if existing.is_banned:
            raise HTTPException(status_code=403, detail="Account banned")

        token = auth.create_token({"user_id": existing.id})
        existing.last_login_at = datetime.now(timezone.utc)
        db.add(existing)
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
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/api/auth/me")
def me(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
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
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }

@app.get("/api/detections")
def get_detections(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user.get("user_id")
    detections = db.query(models.Detection).filter(
        models.Detection.user_id == user_id
    ).order_by(models.Detection.timestamp.desc()).limit(100).all()
    return detections

@app.get("/api/sessions")
def get_sessions(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user.get("user_id")
    sessions = db.query(models.Session).filter(
        models.Session.user_id == user_id
    ).order_by(models.Session.start_time.desc()).limit(50).all()
    return sessions

@app.get("/api/alerts")
def get_alerts(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user.get("user_id")
    alerts = db.query(models.Alert).filter(
        models.Alert.user_id == user_id
    ).order_by(models.Alert.timestamp.desc()).limit(100).all()
    return alerts

@app.get("/api/search-queries")
def get_search_queries(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user.get("user_id")
    queries = db.query(models.SearchQuery).filter(
        models.SearchQuery.user_id == user_id
    ).order_by(models.SearchQuery.timestamp.desc()).limit(100).all()
    return queries

@app.get("/api/preferences")
def get_preferences(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    user_id = user.get("user_id")
    prefs = db.query(models.UserPreference).filter(
        models.UserPreference.user_id == user_id
    ).first()
    if not prefs:
        return {"tts_speed": 1, "default_mode": "navigation", "voice": "default", "theme": "dark"}
    return prefs

@app.post("/api/preferences")
def save_preferences(prefs: schemas.UserPreferenceSchema, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
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
    user_id = user.get("user_id")
    commands = db.query(models.VoiceCommand).filter(
        models.VoiceCommand.user_id == user_id
    ).order_by(models.VoiceCommand.timestamp.desc()).limit(100).all()
    return commands

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/api/ui-config")
def ui_config(db: Session = Depends(get_db)):
    """Public toggles driving detection overlay rendering (no auth needed —
    consumed by the live camera overlay on every feature page)."""
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


# =========================
# SCENE DESCRIPTION (VISION LLM)
# =========================
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
    """Build a natural-language scene description + speech text from the
    vision pipeline objects detected in the captured frame."""
    if not objects:
        desc = (
            "I don't see any clearly recognisable objects in this scene. "
            "The frame appears to be empty or low-light."
        )
        return desc, (
            "I don't see any recognisable objects in this frame. "
            "You may want to point towards something and try again."
        )

    by_class = {}
    for obj in objects:
        name = SCENE_NAMES.get(obj.class_name.lower(), obj.class_name)
        by_class.setdefault(name, []).append(obj)

    # Dominant objects, sorted by count then confidence.
    ranked = sorted(
        by_class.items(),
        key=lambda kv: (-len(kv[1]), -max(o.confidence for o in kv[1])),
    )

    parts = []
    for name, objs in ranked[:3]:
        count = len(objs)
        sample = max(objs, key=lambda o: o.confidence)
        side = ""
        if sample.horizontal_offset_norm is not None:
            if sample.horizontal_offset_norm < -0.25:
                side = " on your left"
            elif sample.horizontal_offset_norm > 0.25:
                side = " on your right"

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

    if len(parts) == 1:
        detail = parts[0]
    elif len(parts) == 2:
        detail = f"{parts[0]} and {parts[1]}"
    else:
        detail = f"{parts[0]}, {parts[1]}, and {parts[2]}"

    total = sum(len(v) for v in by_class.values())
    human = sum(len(v) for k, v in by_class.items() if "person" in k)

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
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    raw = await file.read()
    try:
        arr = np.frombuffer(raw, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Could not decode uploaded image")

    if frame is None or frame.size == 0:
        raise HTTPException(status_code=400, detail="Could not decode uploaded image")

    # A single captured frame analysis — clear any left-over search target so
    # detection uses the normal confidence threshold.
    import App.api.websocket as ws_mod
    ws_mod.SEARCH_TARGET = None

    start = time_mod.time()
    try:
        event = await asyncio.to_thread(perception.process_frame, frame)
    except Exception as e:
        logger.error(f"Scene analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Scene analysis failed")

    objects = list(event.payload.active_objects.values())
    description, speech_text = _describe_scene(objects)

    # Paid users get LLM-powered description when a key is configured; free
    # users keep the rule-based text. Any failure falls back to rule-based.
    db = SessionLocal()
    try:
        urow = db.query(models.User).filter(models.User.id == user.get("user_id")).first()
        if urow:
            from App.core.llm import build_scene_description
            description, _used_llm = build_scene_description(
                db, urow, frame, description,
                objects=[
                    {"label": o.class_name, "confidence": round(float(o.confidence), 2)}
                    for o in objects
                ],
            )
            if _used_llm and description:
                speech_text = description
    finally:
        db.close()

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
    text = (payload.speech_text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="speech_text is required")

    try:
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

# ---------------------------------------------------------------------------
# INFERENCE PIPELINE (backend + models are resolved from admin settings)
# ---------------------------------------------------------------------------
def _vision_settings():
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


_vs = _vision_settings()
INFERENCE_BACKEND = resolve_backend(_vs["backend"])
logger.info(f"[Inference] active backend: {INFERENCE_BACKEND} ({describe_backend(INFERENCE_BACKEND)})")

bus = AsyncEventBus()
tracker = ObjectTracker(imgsz=_vs["imgsz"])
depth_model = create_depth_estimator(INFERENCE_BACKEND, _vs["quality"], _DEFAULT_ONNX_PATH())
depth_provider = DepthUpdater(depth_model, refresh_sec=_vs["refresh_ms"] / 1000.0)
perception = PerceptionSystem(tracker=tracker, depth_provider=depth_provider)
tts_announcer = DetectionTTSAnnouncer()

@app.on_event("startup")
async def startup():
    logger.info("Starting AI system...")

    reasoning = ReasoningLayer(bus)
    rule_engine = RuleEngine(bus)
    scheduler = SpeechScheduler(bus, cooldown_sec=0.1)

    await bus.subscribe("PERCEPTION_FRAME_READY", send_detections)
    await bus.subscribe("PERCEPTION_FRAME_READY", reasoning.handle_event)
    await bus.subscribe("PERCEPTION_FRAME_READY", tts_announcer.handle_frame)
    await bus.subscribe("FRAME_ANALYSIS_READY", rule_engine.handle_event)

    await scheduler.start()
    await tts_announcer.start()
    await depth_provider.start()
    logger.info("System ready")

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    logger.info("WebSocket connection request")
    await register_client(ws)
    await receive_frames(ws, perception, bus)
