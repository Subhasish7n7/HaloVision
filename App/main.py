from fastapi import FastAPI, WebSocket
import logging

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
# LOGGING
# =========================
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# =========================
# APP
# =========================
app = FastAPI()

# =========================
# GLOBALS
# =========================
bus = AsyncEventBus()

tracker = ObjectTracker()
depth_model = MiDaSDepthEstimator()

perception = PerceptionSystem(
    tracker=tracker,
    depth_model=depth_model
)

# =========================
# STARTUP
# =========================
@app.on_event("startup")
async def startup():
    print("🚀 Starting system...")

    reasoning = ReasoningLayer(bus)
    rule_engine = RuleEngine(bus)
    scheduler = SpeechScheduler(bus, cooldown_sec=0.1)

    print("📡 Subscribing handlers...")

    # ✅ CORE PIPELINE
    await bus.subscribe("PERCEPTION_FRAME_READY", send_detections)
    await bus.subscribe("PERCEPTION_FRAME_READY", reasoning.handle_event)

    await bus.subscribe("FRAME_ANALYSIS_READY", rule_engine.handle_event)

    # 🔊 Scheduler (internal subscriptions)
    await scheduler.start()

    print("✅ SYSTEM READY")

# =========================
# WEBSOCKET
# =========================
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    print("🌐 WebSocket connected")

    await register_client(ws)
    await receive_frames(ws, perception, bus)