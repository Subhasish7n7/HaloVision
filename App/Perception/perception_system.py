import time
import uuid
from typing import Dict
import numpy as np
import logging
import asyncio

# 🔥 IMPORTANT FIX
from App.api.websocket import SEARCH_TARGET, send_speech_text

from App.core.contracts import (
    ObjectData,
    TrackingState,
    SystemEvent,
)

logger = logging.getLogger(__name__)


class PerceptionSystem:

    def __init__(self, tracker, depth_model):
        self.tracker = tracker
        self.depth_model = depth_model

        self.frame_id = 0
        self.first_seen: Dict[str, float] = {}
        self.last_depth = None

        self.last_spoken = ""

    # =========================
    # MAIN PIPELINE
    # =========================
    def process_frame(self, frame):
        start_total = time.time()
        timestamp = time.time()
        self.frame_id += 1

        h, w = frame.shape[:2]

        # =========================
        # 1. TRACKING
        # =========================
        t1 = time.time()
        tracks, _ = self.tracker.track(frame)
        logger.debug(f"[PERF] tracking={(time.time() - t1)*1000:.1f}ms")

        # =========================
        # 2. DEPTH (OPTIMIZED)
        # =========================
        t2 = time.time()

        if self.frame_id % 3 == 0 or self.last_depth is None:
            try:
                self.last_depth = self.depth_model.predict(frame)
            except Exception as e:
                logger.error(f"Depth error: {e}")
                self.last_depth = None

        depth_map = self.last_depth

        logger.debug(f"[PERF] depth={(time.time() - t2)*1000:.1f}ms")

        # =========================
        # 3. BUILD OBJECTS
        # =========================
        active_objects = {}

        for track in tracks:
            obj = self._build_object_data(
                track=track,
                depth_map=depth_map,
                frame_width=w,
                frame_height=h,
                timestamp=timestamp,
            )

            if obj is None:
                continue

            # 🔥 FIXED FILTER (IMPORTANT)
            if SEARCH_TARGET:
                if SEARCH_TARGET in obj.class_name.lower():
                    active_objects[obj.object_id] = obj
            else:
                active_objects[obj.object_id] = obj

        logger.debug(f"[INFO] objects={len(active_objects)}")

        # =========================
        # 🔊 SPEECH (SEARCH MODE)
        # =========================
        if SEARCH_TARGET and len(active_objects) > 0:
            text = f"{SEARCH_TARGET} found"

            if text != self.last_spoken:
                self.last_spoken = text
                asyncio.create_task(send_speech_text(text))

        if len(active_objects) == 0:
            self.last_spoken = ""

        # =========================
        # 4. STATE
        # =========================
        state = TrackingState(
            active_objects=active_objects,
            frame_id=self.frame_id,
            timestamp=timestamp,
        )

        # =========================
        # 5. EVENT
        # =========================
        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type="PERCEPTION_FRAME_READY",
            payload=state,
            priority=1,
            timestamp=timestamp,
        )

        logger.debug(f"[PERF] total={(time.time() - start_total)*1000:.1f}ms")

        return event

    # =========================
    # OBJECT BUILDER
    # =========================
    def _build_object_data(
        self,
        track,
        depth_map,
        frame_width,
        frame_height,
        timestamp,
    ):
        try:
            x1, y1, x2, y2 = map(int, track.bbox)

            # clamp
            x1 = max(0, min(x1, frame_width - 1))
            x2 = max(0, min(x2, frame_width - 1))
            y1 = max(0, min(y1, frame_height - 1))
            y2 = max(0, min(y2, frame_height - 1))

            if x2 <= x1 or y2 <= y1:
                return None

            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            horizontal_offset = (cx - frame_width / 2) / (frame_width / 2)
            horizontal_offset = float(np.clip(horizontal_offset, -1.0, 1.0))

            # 🔥 SAFE DEPTH
            if depth_map is not None:
                depth_norm, depth_conf = self._extract_depth(
                    depth_map, x1, y1, x2, y2
                )
            else:
                depth_norm, depth_conf = 0.0, 0.0

            object_id = f"track_{track.track_id}"

            if object_id not in self.first_seen:
                self.first_seen[object_id] = timestamp

            return ObjectData(
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

        except Exception as e:
            logger.error(f"Object build error: {e}")
            return None

    # =========================
    # DEPTH EXTRACTOR
    # =========================
    def _extract_depth(self, depth_map, x1, y1, x2, y2):
        region = depth_map[y1:y2, x1:x2]

        if region.size == 0:
            return 0.0, 0.0

        depth = float(np.mean(region))
        return depth, 1.0