import time
import uuid
from typing import Dict

import numpy as np

from App.core.contracts import (
    ObjectData,
    TrackingState,
    SystemEvent,
)


class PerceptionSystem:
    def __init__(self, detector, tracker, depth_model):
        """
        detector: YOLO-like model → returns detections
        tracker: ByteTrack-like tracker → returns tracked objects
        depth_model: MiDaS-like model → returns depth map
        """
        self.detector = detector
        self.tracker = tracker
        self.depth_model = depth_model

        self.frame_id = 0

        # Track lifecycle memory
        self.first_seen: Dict[str, float] = {}

    # -----------------------------
    # Main entry point
    # -----------------------------
    def process_frame(self, frame: np.ndarray) -> SystemEvent:
        timestamp = time.time()
        self.frame_id += 1

        h, w = frame.shape[:2]

        # 1. Detect
        detections = self.detector.detect(frame)

        # 2. Track
        tracks = self.tracker.update(detections)

        # 3. Depth
        depth_map = self.depth_model.predict(frame)
        depth_map = self._normalize_depth(depth_map)

        # 4. Build objects
        active_objects = {}

        for track in tracks:
            obj = self._build_object_data(
                track=track,
                depth_map=depth_map,
                frame_width=w,
                frame_height=h,
                timestamp=timestamp,
            )

            if obj is not None:
                active_objects[obj.object_id] = obj

        # 5. Build state
        state = TrackingState(
            active_objects=active_objects,
            frame_id=self.frame_id,
            timestamp=timestamp,
        )

        # 6. Emit event
        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type="PERCEPTION_FRAME_READY",
            payload=state,
            priority=1,
            timestamp=timestamp,
        )

        return event

    # -----------------------------
    # Object Builder
    # -----------------------------
    def _build_object_data(
        self,
        track,
        depth_map: np.ndarray,
        frame_width: int,
        frame_height: int,
        timestamp: float,
    ) -> ObjectData | None:
        """
        track expected fields:
            track_id
            bbox (x1, y1, x2, y2)
            class_name
            confidence
        """

        x1, y1, x2, y2 = map(int, track.bbox)

        # Clamp bbox to frame
        x1 = max(0, min(x1, frame_width - 1))
        x2 = max(0, min(x2, frame_width - 1))
        y1 = max(0, min(y1, frame_height - 1))
        y2 = max(0, min(y2, frame_height - 1))

        if x2 <= x1 or y2 <= y1:
            return None

        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)

        # Horizontal offset [-1, 1]
        horizontal_offset = (cx - frame_width / 2) / (frame_width / 2)
        horizontal_offset = float(np.clip(horizontal_offset, -1.0, 1.0))

        # Depth extraction
        depth_norm, depth_conf = self._extract_depth(
            depth_map, x1, y1, x2, y2
        )

        object_id = f"track_{track.track_id}"

        # Lifecycle tracking
        if object_id not in self.first_seen:
            self.first_seen[object_id] = timestamp

        obj = ObjectData(
            object_id=object_id,
            class_name=track.class_name,
            confidence=float(track.confidence),
            bbox=(x1, y1, x2, y2),
            centroid=(cx, cy),

            depth_norm=float(depth_norm),
            depth_confidence=float(depth_conf),

            horizontal_offset_norm=horizontal_offset,

            velocity_norm=None,
            direction_vector=None,
            is_stationary=False,
            is_moving_towards_user=False,

            first_seen_ts=self.first_seen[object_id],
            last_seen_ts=timestamp,
            frame_timestamp=timestamp,
        )

        return obj

    # -----------------------------
    # Depth helpers
    # -----------------------------
    def _normalize_depth(self, depth_map: np.ndarray) -> np.ndarray:
        """
        Normalize depth to [0, 1]
        0 → far, 1 → near (IMPORTANT)
        """
        if depth_map is None or depth_map.size == 0:
            return depth_map

        d_min = np.min(depth_map)
        d_max = np.max(depth_map)

        if d_max - d_min < 1e-6:
            return np.zeros_like(depth_map)

        norm = (depth_map - d_min) / (d_max - d_min)

        # Invert so closer = higher value
        return 1.0 - norm

    def _extract_depth(
        self,
        depth_map: np.ndarray,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
    ) -> tuple[float, float]:
        """
        Robust depth estimation using percentile
        """

        try:
            roi = depth_map[y1:y2, x1:x2]

            if roi.size == 0:
                return 0.0, 0.0

            values = roi.flatten()

            # Remove invalid values
            values = values[np.isfinite(values)]

            if len(values) < 10:
                return 0.0, 0.1

            # Robust estimate (median or percentile)
            depth = float(np.percentile(values, 60))

            # Confidence based on variance
            variance = np.var(values)
            confidence = float(np.clip(1.0 - variance, 0.0, 1.0))

            return depth, confidence

        except Exception:
            return 0.0, 0.0