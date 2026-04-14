from fastapi import FastAPI, WebSocket
import uvicorn

from ultralytics import YOLO

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
    send_audio,
    send_detections,
)


# =========================
# APP
# =========================
app = FastAPI()


# =========================
# YOLO DETECTOR
# =========================
class YOLODetector:
    def __init__(self, model_path):
        self.model = YOLO(model_path)

    def detect(self, frame):
        results = self.model(frame)[0]

        detections = []

        for box in results.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cls = int(box.cls[0])
            conf = float(box.conf[0])

            detections.append(
                type("Det", (), {
                    "bbox": (int(x1), int(y1), int(x2), int(y2)),
                    "class_name": self.model.names[cls],
                    "confidence": conf
                })
            )

        return detections


# =========================
# TRACKER
# =========================
class TrackerAdapter:
    def __init__(self):
        self.tracker = ObjectTracker()
        self.current_frame = None

    def set_frame(self, frame):
        self.current_frame = frame

    def update(self, detections):
        raw_tracks, names = self.tracker.track(self.current_frame)

        adapted = []

        for t in raw_tracks:
            track_id, x1, y1, x2, y2, cls = t

            adapted.append(
                type("Track", (), {
                    "track_id": track_id,
                    "bbox": (int(x1), int(y1), int(x2), int(y2)),
                    "class_name": names[cls],
                    "confidence": 1.0
                })
            )

        return adapted


# =========================
# GLOBALS
# =========================
bus = AsyncEventBus()

tracker = TrackerAdapter()

detector = YOLODetector("App/yolov8m.pt")

perception = PerceptionSystem(
    detector=detector,
    tracker=tracker,
    depth_model=MiDaSDepthEstimator(),
)


# =========================
# STARTUP
# =========================
@app.on_event("startup")
async def startup():
    reasoning = ReasoningLayer(bus)
    rule = RuleEngine(bus)
    scheduler = SpeechScheduler(bus, cooldown_sec=0.1)

    # Perception → reasoning + frontend
    await bus.subscribe("PERCEPTION_FRAME_READY", reasoning.handle_event)
    await bus.subscribe("PERCEPTION_FRAME_READY", send_detections)

    # Reasoning → rule engine
    await bus.subscribe("FRAME_ANALYSIS_READY", rule.handle_event)

    # 🚫 DO NOT manually subscribe scheduler here
    # scheduler.start() already does it internally

    await scheduler.start()

    # Speech → frontend
    await bus.subscribe("SPEECH_AUDIO_READY", send_audio)

    print("✅ SYSTEM READY")


# =========================
# WEBSOCKET
# =========================
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await register_client(ws)
    await receive_frames(ws, perception, tracker, bus)


# =========================
# RUN
# =========================
if __name__ == "__main__":
    uvicorn.run("App.main:app", host="127.0.0.1", port=8000, reload=True)