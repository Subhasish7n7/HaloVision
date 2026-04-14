from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import numpy as np
import cv2
import json
import traceback

from ultralytics import YOLO

from App.core.event_bus import AsyncEventBus
from App.core.reasoning_layer import ReasoningLayer
from App.core.rule_engine import RuleEngine

from App.Perception.perception_system import PerceptionSystem
from App.Perception.tracker import ObjectTracker
from App.Perception.depth_estimator import MiDaSDepthEstimator

app = FastAPI()

connected_clients = set()
bus = None


# =========================
# ✅ YOLO DETECTOR (FIXED)
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
# INIT SYSTEMS
# =========================
tracker = TrackerAdapter()

# ✅ FIX: REAL DETECTOR
detector = YOLODetector("App/yolov8m.pt")

perception = PerceptionSystem(
    detector=detector,   # 🔥 FIXED HERE
    tracker=tracker,
    depth_model=MiDaSDepthEstimator(),
)


# =========================
# EVENT SYSTEM
# =========================
async def forward_speech(event):
    intent = event.payload

    message = json.dumps({
        "type": "voice",
        "text": intent.text,
        "priority": intent.priority,
    })

    for ws in list(connected_clients):
        try:
            await ws.send_text(message)
        except:
            connected_clients.discard(ws)


async def setup():
    global bus

    bus = AsyncEventBus()

    reasoning = ReasoningLayer(bus)
    rule = RuleEngine(bus)

    await bus.subscribe("PERCEPTION_FRAME_READY", reasoning.handle_event)
    await bus.subscribe("FRAME_ANALYSIS_READY", rule.handle_event)
    await bus.subscribe("USER_COMMAND_RECEIVED", rule.handle_event)
    await bus.subscribe("SPEECH_INTENT_CREATED", forward_speech)

    print("✅ FULL PIPELINE CONNECTED")


@app.on_event("startup")
async def startup():
    await setup()


# =========================
# WEBSOCKET
# =========================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)

    print("✅ Client connected")

    try:
        while True:
            # 📸 RECEIVE FRAME
            data = await websocket.receive_bytes()

            np_arr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame is None:
                continue

            # 🔥 PERCEPTION
            tracker.set_frame(frame)
            event = perception.process_frame(frame)

            if bus:
                await bus.publish(event, await_handlers=True)

            objects = event.payload.active_objects
            h, w = frame.shape[:2]

            detections = []

            for obj in objects.values():
                x1, y1, x2, y2 = obj.bbox

                detections.append({
                    "x": x1 / w,
                    "y": y1 / h,
                    "width": (x2 - x1) / w,
                    "height": (y2 - y1) / h,
                    "label": f"{obj.class_name} {obj.depth_m:.2f}",
                    "id": obj.object_id
                })

            # 📤 SEND RESULT
            await websocket.send_text(json.dumps(detections))

    except WebSocketDisconnect:
        print("🔌 Client disconnected")

    except Exception as e:
        print("❌ Error:", e)
        traceback.print_exc()

    finally:
        connected_clients.discard(websocket)