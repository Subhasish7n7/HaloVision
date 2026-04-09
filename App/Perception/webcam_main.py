import cv2
import asyncio
import time
import uuid
import torch

from App.core.event_bus import AsyncEventBus
from App.core.reasoning_layer import ReasoningLayer
from App.core.rule_engine import RuleEngine
from App.core.contracts import ObjectData, TrackingState, SystemEvent

from depth_estimator import MiDaSDepthEstimator
from fusion import compute_object_depth
from tracker import ObjectTracker
from speed import SpeedEstimator

from tts import tts


# ============================================================
# 🔊 SPEECH LISTENER
# ============================================================

async def speech_listener(event):
    intent = event.payload

    print("\n🧠 FINAL DECISION")
    print(f"Category : {intent.category}")
    print(f"Priority : {intent.priority}")
    print(f"Text     : {intent.text}")

    tts.speak(intent.text)


# ============================================================
# 🔌 SYSTEM SETUP
# ============================================================

async def setup_system():
    bus = AsyncEventBus()

    reasoning = ReasoningLayer(bus)
    rule_engine = RuleEngine(bus)

    await bus.subscribe("PERCEPTION_FRAME_READY", reasoning.handle_event)
    await bus.subscribe("FRAME_ANALYSIS_READY", rule_engine.handle_event)
    await bus.subscribe("SPEECH_INTENT_CREATED", speech_listener)

    return bus


# ============================================================
# 🎥 MAIN LOOP
# ============================================================

async def run_camera():

    print("\n===== DEVICE CHECK =====")
    print("CUDA Available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("GPU:", torch.cuda.get_device_name(0))
    print("========================\n")

    bus = await setup_system()

    cap = cv2.VideoCapture(0)

    depth_model = MiDaSDepthEstimator()
    tracker = ObjectTracker()
    speed_estimator = SpeedEstimator()

    frame_id = 0
    depth_map = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.resize(frame, (416, 320))
        h, w = frame.shape[:2]

        print("\n" + "=" * 50)
        print(f"🎥 FRAME {frame_id}")

        # ====================================================
        # ⚡ PERFORMANCE: run depth every 3 frames
        # ====================================================
        if frame_id % 3 == 0 or depth_map is None:
            depth_map = depth_model.predict(frame)

        tracks, class_names = tracker.track(frame)

        objects = {}

        print("\n👁️ PERCEPTION OUTPUT")

        for track in tracks:

            track_id, x1, y1, x2, y2, cls = track
            label = class_names[cls]

            depth_val = compute_object_depth(depth_map, (x1, y1, x2, y2))
            if depth_val is None:
                continue

            # depth scaling (approx meters)
            depth_m = float(1.0 + (1.0 - depth_val) * 4.0)

            # speed
            speed = speed_estimator.estimate(track_id, depth_m)

            # horizontal offset
            cx = (x1 + x2) / 2
            offset = (cx - w / 2) / (w / 2)

            # ✅ FIXED: class_name instead of label
            obj = ObjectData(
                object_id=str(track_id),
                class_name=label,
                confidence=0.9,
                bbox=(int(x1), int(y1), int(x2), int(y2)),
                centroid=(int(cx), int((y1 + y2) / 2)),
                depth_m=depth_m,
                depth_confidence=0.9,
                horizontal_offset_norm=offset,
                velocity_mps=speed,
                last_seen_ts=time.time(),
            )

            objects[obj.object_id] = obj

            print(
                f"{label} | "
                f"Depth={depth_m:.2f}m | "
                f"Speed={speed:.2f} | "
                f"Offset={offset:.2f}"
            )

        # ====================================================
        # 📡 SEND TO REASONING
        # ====================================================

        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type="PERCEPTION_FRAME_READY",
            payload=TrackingState(objects, frame_id, time.time()),
            priority=1,
            timestamp=time.time(),
        )

        await bus.publish(event)

        frame_id += 1

        cv2.imshow("HeloVision AI", frame)

        if cv2.waitKey(1) & 0xFF == 27:
            break

    cap.release()
    cv2.destroyAllWindows()


# ============================================================
# 🚀 MAIN
# ============================================================

if __name__ == "__main__":
    asyncio.run(run_camera())