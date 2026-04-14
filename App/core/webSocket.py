from fastapi import FastAPI, WebSocket
import base64
import numpy as np
import cv2
import json

from App.core.event_bus import AsyncEventBus
from App.core.contracts import SystemEvent
from App.Perception.perception_system import PerceptionSystem
from App.Perception.tracker import ObjectTracker
from App.Perception.depth_estimator import MiDaSDepthEstimator

# =========================
# APP + GLOBALS
# =========================
app = FastAPI()
connected_clients: list[WebSocket] = []
bus = AsyncEventBus()


# =========================
# TRACKER ADAPTER
# =========================
class TrackerAdapter:
    def __init__(self):
        self.tracker = ObjectTracker()
        self.current_frame = None

    def set_frame(self, frame):
        self.current_frame = frame

    def update(self, detections):
        raw_tracks, names = self.tracker.track(self.current_frame)

        adapted_tracks = []

        for t in raw_tracks:
            track_id, x1, y1, x2, y2, cls = t

            adapted_tracks.append(
                type("Track", (), {
                    "track_id": track_id,
                    "bbox": (int(x1), int(y1), int(x2), int(y2)),
                    "class_name": names[cls],
                    "confidence": 1.0
                })
            )

        return adapted_tracks


# =========================
# INIT PERCEPTION
# =========================
tracker = TrackerAdapter()

perception = PerceptionSystem(
    detector=None,
    tracker=tracker,
    depth_model=MiDaSDepthEstimator(),
)


# =========================
# 🔊 EVENT → FRONTEND (VOICE)
# =========================
async def speech_listener(event: SystemEvent):
    intent = event.payload

    message = {
        "type": "voice",
        "text": intent.text,
        "priority": intent.priority,
    }

    for ws in connected_clients:
        try:
            await ws.send_text(json.dumps(message))
        except:
            pass


# =========================
# 🔁 REGISTER EVENT LISTENER
# =========================
@app.on_event("startup")
async def startup_event():
    await bus.subscribe("SPEECH_INTENT_CREATED", speech_listener)
    print("✅ Speech listener connected")


# =========================
# 🔌 WEBSOCKET
# =========================
@app.websocket("/ws")
async def websocket_handler(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)

    print("✅ Frontend connected")

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            # =========================
            # 📸 Decode Image
            # =========================
            image_data = message["image"].split(",")[1]
            img_bytes = base64.b64decode(image_data)

            np_arr = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame is None:
                continue

            # =========================
            # 🔥 PERCEPTION
            # =========================
            tracker.set_frame(frame)
            event = perception.process_frame(frame)

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

            # =========================
            # 📤 SEND DETECTIONS
            # =========================
            await websocket.send_text(json.dumps(detections))

            # =========================
            # 🔁 (OPTIONAL) TRIGGER EVENT
            # =========================
            # Example test:
            # await bus.publish(SystemEvent(
            #     event_id="1",
            #     event_type="SPEECH_INTENT_CREATED",
            #     payload=type("obj", (), {"text": "Object detected", "priority": 2}),
            #     priority=1,
            #     timestamp=0
            # ))

    except Exception as e:
        print("❌ Error:", e)

    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)

        print("🔌 Client disconnected")