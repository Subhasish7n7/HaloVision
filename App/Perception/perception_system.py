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

# Model is loaded once; only the confidence threshold changes per mode, so
# starting a search never restarts/reloads the detector.
NORMAL_CONFIDENCE = 0.45
SEARCH_CONFIDENCE = 0.25


class PerceptionSystem:

    def __init__(self, tracker, depth_provider):
        self.tracker = tracker
        self.depth_provider = depth_provider

        self.frame_id = 0
        self.first_seen: Dict[str, float] = {}
        self.last_depth = None

        self.last_spoken = ""

        self._last_infer_ms = 0.0
        self._fps = 0.0
        self._perf_last = None

    def perf_stats(self) -> dict:
        # Frame-rate estimate: instantaneous delta between consecutive reads,
        # smoothed with an EMA. Unlike a rolling timestamp window this stays
        # correct even when frames arrive in bursts (WS decode + to_thread).
        now = time.time()
        if self._perf_last is not None:
            dt = now - self._perf_last
            if dt > 0.01:
                inst = 1.0 / dt
                self._fps = self._fps * 0.8 + inst * 0.2 if self._fps else inst
        self._perf_last = now

        return {
            "fps": round(self._fps, 1),
            "infer_ms": round(self._last_infer_ms, 1),
            "depth_ms": round(getattr(self.depth_provider, "last_ms", lambda: 0.0)(), 1),
        }

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
        # Continuous background detection. Search mode relaxes the confidence
        # threshold (earlier acquisition) without touching the model itself.
        conf = SEARCH_CONFIDENCE if SEARCH_TARGET else NORMAL_CONFIDENCE
        t1 = time.time()
        tracks, _ = self.tracker.track(frame, conf=conf)
        self._last_infer_ms = (time.time() - t1) * 1000

        # =========================
        # 2. DEPTH (ASYNC — NEVER BLOCKS DETECTION)
        # =========================
        # The DepthUpdater owns inference; we just read the freshest map.
        # Detection speed is therefore independent of depth-model latency.
        if getattr(self.depth_provider, "feed", None) is not None:
            self.depth_provider.feed(frame)
        depth_map = self.depth_provider.current()

        # =========================
        # 3. BUILD OBJECTS (ALWAYS ALL)
        # =========================
        # Every detected object is tracked continuously so the frontend can
        # highlight matches instantly. Search just filters *rendering*.
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

            active_objects[obj.object_id] = obj

        # Collapse duplicate/ghost detections: when two boxes of the same
        # class overlap heavily (split or re-initialized tracks from YOLO /
        # ByteTrack), keep only the highest-confidence one so one person
        # never renders as two boxes.
        active_objects = self._dedupe_overlapping(active_objects)

        # =========================
        # SEARCH MATCHES + SPEECH
        # =========================
        search_matches = {}

        if SEARCH_TARGET:
            for oid, obj in active_objects.items():
                if SEARCH_TARGET in obj.class_name.lower():
                    search_matches[oid] = obj

        if SEARCH_TARGET and len(search_matches) > 0:
            text = f"{SEARCH_TARGET} found"

            if text != self.last_spoken:
                self.last_spoken = text
                asyncio.create_task(send_speech_text(text))

        if len(search_matches) == 0:
            self.last_spoken = ""

        logger.debug(f"[INFO] objects={len(active_objects)} matches={len(search_matches)}")

        # =========================
        # 4. STATE
        # =========================
        state = TrackingState(
            active_objects=active_objects,
            frame_id=self.frame_id,
            timestamp=timestamp,
            perf=self.perf_stats(),
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
    # DUPLICATE DETECTION MERGE
    # =========================
    @staticmethod
    def _iou(a, b):
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        inter = iw * ih
        if inter == 0:
            return 0.0
        a_area = (ax2 - ax1) * (ay2 - ay1)
        b_area = (bx2 - bx1) * (by2 - by1)
        union = a_area + b_area - inter
        return inter / union if union > 0 else 0.0

    def _dedupe_overlapping(self, active_objects):
        """Merge same-class detections whose boxes overlap (IoU >= 0.5),
        keeping the highest-confidence box per person/object."""
        items = list(active_objects.values())
        dropped = set()
        merged = {}

        for i, obj in enumerate(items):
            if obj.object_id in dropped:
                continue
            for other in items[i + 1:]:
                if other.object_id in dropped:
                    continue
                if other.class_name != obj.class_name:
                    continue
                if self._iou(obj.bbox, other.bbox) >= 0.5:
                    if other.confidence > obj.confidence:
                        dropped.add(obj.object_id)
                        obj = other
                    else:
                        dropped.add(other.object_id)
            merged[obj.object_id] = obj

        return merged

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

                track_id=int(track.track_id),
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