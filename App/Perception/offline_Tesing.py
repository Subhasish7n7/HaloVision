import cv2
import asyncio
import time
import uuid

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
# 🔊 SPEECH OUTPUT
# ============================================================

async def speech_listener(event):
    intent = event.payload

    print("\n🧠 FINAL DECISION")
    print(f"Category : {intent.category}")
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
# 🚗 VEHICLE FILTER
# ============================================================

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "bicycle"}


def is_vehicle(label):
    return label.lower() in VEHICLE_CLASSES


# ============================================================
# 🎥 PROCESS IMAGE / VIDEO
# ============================================================

async def process_input(source_path):

    bus = await setup_system()

    depth_model = MiDaSDepthEstimator()
    tracker = ObjectTracker()
    speed_estimator = SpeedEstimator()

    is_image = source_path.lower().endswith((".jpg", ".png", ".jpeg"))

    if is_image:
        frame = cv2.imread(source_path)
        frames = [frame]
    else:
        cap = cv2.VideoCapture(source_path)

    frame_id = 0
    depth_map = None

    while True:

        if is_image:
            if frame_id > 0:
                break
            frame = frames[0]
        else:
            ret, frame = cap.read()
            if not ret:
                break

        frame = cv2.resize(frame, (416, 320))
        h, w = frame.shape[:2]

        print("\n" + "=" * 50)
        print(f"🎥 FRAME {frame_id}")

        # ---------------- DEPTH ----------------
        if frame_id % 3 == 0 or depth_map is None:
            depth_map = depth_model.predict(frame)

        tracks, class_names = tracker.track(frame)

        objects = {}

        print("\n👁️ PERCEPTION OUTPUT")

        for track in tracks:
            track_id, x1, y1, x2, y2, cls = track
            label = class_names[cls]

            # 🚗 FILTER VEHICLES ONLY
            if not is_vehicle(label):
                continue

            depth_val = compute_object_depth(depth_map, (x1, y1, x2, y2))
            if depth_val is None:
                continue

            depth_m = float(1.0 + (1.0 - depth_val) * 4.0)
            speed = speed_estimator.estimate(track_id, depth_m)

            cx = (x1 + x2) / 2
            offset = (cx - w / 2) / (w / 2)

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
                f"{label} | Depth={depth_m:.2f} | "
                f"Speed={speed:.2f} | Offset={offset:.2f}"
            )

        # ====================================================
        # 🚨 FIX: SKIP EMPTY FRAMES (VERY IMPORTANT)
        # ====================================================
        if not objects:
            print("⚠️ No vehicles detected → skipping frame")
        else:
            event = SystemEvent(
                event_id=str(uuid.uuid4()),
                event_type="PERCEPTION_FRAME_READY",
                payload=TrackingState(objects, frame_id, time.time()),
                priority=1,
                timestamp=time.time(),
            )

            await bus.publish(event)

        # ---------------- DISPLAY ----------------
        cv2.imshow("Vehicle Mode", frame)

        if cv2.waitKey(1) & 0xFF == 27:
            break

        frame_id += 1

    if not is_image:
        cap.release()

    cv2.destroyAllWindows()


# ============================================================
# 🚀 MAIN
# ============================================================

if __name__ == "__main__":

    # 🔥 CHANGE THIS
    SOURCE = "../../images/MeInCollege.jpeg"
    # SOURCE = "test_image.jpg"

    asyncio.run(process_input(SOURCE))