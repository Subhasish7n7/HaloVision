import cv2
import asyncio

from App.Perception.perception_system import PerceptionSystem
from App.Perception.tracker import ObjectTracker
from App.Perception.depth_estimator import MiDaSDepthEstimator


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


class DummyDetector:
    def detect(self, frame):
        return []


async def process_frame(bus):

    tracker = TrackerAdapter()

    perception = PerceptionSystem(
        detector=DummyDetector(),
        tracker=tracker,
        depth_model=MiDaSDepthEstimator(),
    )

    cap = cv2.VideoCapture(0)

    if not cap.isOpened():
        raise Exception("Camera not accessible")

    print("🚀 Perception running...")

    try:
        while True:
            ret, frame = cap.read()

            if not ret:
                continue

            tracker.set_frame(frame)

            event = perception.process_frame(frame)

            # 🔥 ===== PERCEPTION LOG =====
            print("\n[PERCEPTION OUTPUT]")
            for obj in event.payload.active_objects.values():
                print(
                    f"{obj.object_id} | {obj.class_name} | "
                    f"depth={obj.depth_m:.2f} | offset={obj.horizontal_offset_norm:.2f}"
                )

            # 🔥 Draw on screen
            for obj in event.payload.active_objects.values():
                x1, y1, x2, y2 = obj.bbox

                label = f"{obj.class_name} {obj.depth_m:.2f}"

                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, label, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            cv2.imshow("Perception", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            await bus.publish(event)
            await asyncio.sleep(0)

    finally:
        cap.release()
        cv2.destroyAllWindows()