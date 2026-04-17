from fastapi import FastAPI, WebSocket, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import logging

# =========================
# 🔐 AUTH IMPORTS
# =========================
from App.api.database import SessionLocal, engine
from App.api import models, schemas, auth

# =========================
# 🤖 AI SYSTEM IMPORTS
# =========================
from App.core.event_bus import AsyncEventBus
from App.core.reasoning_layer import ReasoningLayer
from App.core.rule_engine import RuleEngine
from App.core.speech_scheduler import SpeechScheduler

from App.Perception.perception_system import PerceptionSystem
from App.Perception.tracker import ObjectTracker
from App.Perception.depth_estimator import MiDaSDepthEstimator

from App.api.websocket import (
    register_client,
    receive_frames,
    send_detections,
)

# =========================
# 🧠 APP INIT
# =========================
app = FastAPI()

# =========================
# 🌐 CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# 🗄️ DATABASE INIT
# =========================
print("🗄️ Initializing database...")
models.Base.metadata.create_all(bind=engine)

# =========================
# 🧾 LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# =========================
# 🔗 DB SESSION
# =========================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =========================
# 🔐 AUTH ROUTES
# =========================

@app.post("/api/auth/signup")
def signup(user: schemas.SignupSchema, db: Session = Depends(get_db)):
    try:
        print("🔥 Signup API HIT")

        existing = db.query(models.User).filter(models.User.email == user.email).first()

        if existing:
            raise HTTPException(status_code=400, detail="Email already exists")

        hashed = auth.hash_password(user.password)

        new_user = models.User(
            name=user.name,
            email=user.email,
            password=hashed
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)  # ✅ good practice

        print("✅ User saved")

        return {"message": "User created"}

    except HTTPException:
        raise  # ✅ keep original errors (400, etc.)

    except Exception as e:
        print("💣 ERROR:", str(e))
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.post("/api/auth/login")
def login(user: schemas.LoginSchema, db: Session = Depends(get_db)):
    try:
        print("🔥 Login API HIT")

        existing = db.query(models.User).filter(models.User.email == user.email).first()

        if not existing:
            raise HTTPException(status_code=400, detail="User not found")

        if not auth.verify_password(user.password, existing.password):
            raise HTTPException(status_code=400, detail="Invalid password")

        token = auth.create_token({"user_id": existing.id})

        print("✅ Login success")

        return {"token": token}

    except HTTPException:
        raise

    except Exception as e:
        print("💣 ERROR:", str(e))
        raise HTTPException(status_code=500, detail="Internal Server Error")

# =========================
# 🤖 AI GLOBALS
# =========================
bus = AsyncEventBus()

tracker = ObjectTracker()
depth_model = MiDaSDepthEstimator()

perception = PerceptionSystem(
    tracker=tracker,
    depth_model=depth_model
)

# =========================
# 🚀 STARTUP
# =========================
@app.on_event("startup")
async def startup():
    print("🚀 Starting AI system...")

    reasoning = ReasoningLayer(bus)
    rule_engine = RuleEngine(bus)
    scheduler = SpeechScheduler(bus, cooldown_sec=0.1)

    print("📡 Subscribing handlers...")

    await bus.subscribe("PERCEPTION_FRAME_READY", send_detections)
    await bus.subscribe("PERCEPTION_FRAME_READY", reasoning.handle_event)

    await bus.subscribe("FRAME_ANALYSIS_READY", rule_engine.handle_event)

    await scheduler.start()

    print("✅ SYSTEM READY")

# =========================
# 🔌 WEBSOCKET
# =========================
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    print("🌐 WebSocket connected")

    await register_client(ws)
    await receive_frames(ws, perception, bus)