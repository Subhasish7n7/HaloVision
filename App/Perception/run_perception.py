import cv2
import time
import uuid
import asyncio

from App.core.contracts import ObjectData, TrackingState, SystemEvent

from App.Perception.tracker import ObjectTracker
from App.Perception.depth_estimator import MiDaSDepthEstimator
from App.Perception.fusion import compute_object_depth
from App.Perception.distance import DistanceEstimator
from App.Perception.speed import SpeedEstimator
from App.Perception.visualizer import draw_annotations


async def run_camera_perception(bus):

    # ================= INIT =================
    tracker = ObjectTracker()
    depth_model = MiDaSDepthEstimator()
    distance_estimator = DistanceEstimator()
    speed_estimator = SpeedEstimator()

    cap = cv2.VideoCapture(0)

    frame_id = 0

    print("✅ Camera perception started...")

    # ================= LOOP =================
    while True:

        ret, frame = cap.read()
        if not ret:
            print("❌ Camera read failed")
            break

        frame_id += 1
        now = time.time()

        # ================= TRACKING =================
        tracks, class_names = tracker.track(frame)

        # ================= DEPTH =================
        depth_map = depth_model.predict(frame)

        objects = {}

        distances = {}
        speeds = {}

        # ================= PROCESS EACH OBJECT =================
        for track in tracks:

            track_id, x1, y1, x2, y2, cls = track

            bbox = (int(x1), int(y1), int(x2), int(y2))

            # ---- CENTROID ----
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            # ---- DEPTH ----
            depth_val = compute_object_depth(depth_map, bbox)

            # ---- DISTANCE CATEGORY ----
            dist_label = distance_estimator.estimate(track_id, depth_val, depth_map)

            # ---- SPEED ----
            speed = speed_estimator.estimate(track_id, depth_val if depth_val else 0.0)

            # ---- STORE FOR VISUALIZATION ----
            distances[track_id] = dist_label
            speeds[track_id] = speed

            # ---- NORMALIZED OFFSET (-1 to 1) ----
            frame_w = frame.shape[1]
            offset = (cx - frame_w / 2) / (frame_w / 2)

            # ---- BUILD OBJECT DATA ----
            obj = ObjectData(
                object_id=str(track_id),
                class_name=class_names[cls],
                confidence=1.0,  # tracking confidence implicit
                bbox=bbox,
                centroid=(cx, cy),
                depth_m=float(depth_val) if depth_val is not None else 0.0,
                depth_confidence=1.0 if depth_val is not None else 0.0,
                horizontal_offset_norm=float(offset),
                velocity_mps=float(speed),
                direction_vector=None,
                is_stationary=abs(speed) < 0.01,
                is_moving_towards_user=speed < 0,
                first_seen_ts=now,
                last_seen_ts=now,
                frame_timestamp=now,
            )

            objects[str(track_id)] = obj

        # ================= VISUALIZE =================
        frame = draw_annotations(frame, tracks, distances, speeds, class_names)

        cv2.imshow("Perception Output", frame)

        if cv2.waitKey(1) & 0xFF == 27:
            break

        # ================= CREATE EVENT =================
        tracking_state = TrackingState(
            active_objects=objects,
            frame_id=frame_id,
            timestamp=now
        )

        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type="PERCEPTION_FRAME_READY",
            payload=tracking_state,
            priority=1,
            timestamp=now,
        )

        # ================= PUBLISH =================
        await bus.publish(event, await_handlers=True)

    cap.release()
    cv2.destroyAllWindows()