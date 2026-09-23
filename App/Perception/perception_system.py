# =============================================================================
# FILE: App/Perception/perception_system.py
# ROLE: Main perception pipeline — the brain of the vision system.
#
# WHAT THIS FILE DOES:
#   This is the CORE of the real-time vision pipeline. For every camera frame:
#   1. Runs object detection + tracking (via ObjectTracker)
#   2. Reads the latest depth map (from DepthUpdater — runs asynchronously)
#   3. Builds enriched ObjectData objects (adding depth, position, etc.)
#   4. Removes duplicate/ghost detections (DIoU-based merging)
#   5. Matches objects against search targets (if active)
#   6. Packages everything into a SystemEvent and returns it
#
# FLOW:
#   Camera frame (numpy BGR)
#       ↓
#   ObjectTracker.track() → list of Track objects
#       ↓
#   DepthUpdater.current() → depth map (if available)
#       ↓
#   _build_object_data() → ObjectData per track (with depth, position)
#       ↓
#   _dedupe_overlapping() → remove ghost/duplicate detections
#       ↓
#   Search matching (if SEARCH_TARGET is set)
#       ↓
#   TrackingState → SystemEvent("PERCEPTION_FRAME_READY")
#       ↓
#   EventBus.publish() → fans out to ReasoningLayer, send_detections, TTS
#
# WHO CALLS THIS:
#   - webRTC.py: receive_frames() and _process_rtc_track() call
#     perception.process_frame(frame) for every incoming camera frame
#   - main.py: scene_analyze() calls perception.process_frame(frame)
#     for single-image analysis
#
# KEY DESIGN DECISIONS:
#   - Depth runs ASYNCHRONOUSLY (DepthUpdater) — detection never blocks on depth
#   - Search mode relaxes confidence threshold (0.45 vs 0.55) for faster acquisition
#   - Duplicate merging uses DIoU (Distance-IoU) to avoid merging nearby real objects
# =============================================================================

import time
import uuid
from typing import Dict
import numpy as np
import logging

# Search target comes from webRTC.py — global state shared between transport and perception
from App.api.webRTC import SEARCH_TARGET

# Data contracts define the structure of objects flowing between layers
from App.core.contracts import (
    ObjectData,       # Enriched object with depth, position, velocity
    TrackingState,    # Complete frame state (all objects + metadata)
    SystemEvent,      # Generic event that flows through the EventBus
)

logger = logging.getLogger(__name__)

# Confidence thresholds — search mode uses lower threshold for faster object acquisition
NORMAL_CONFIDENCE = 0.55   # Standard mode: only high-confidence detections
SEARCH_CONFIDENCE = 0.45   # Search mode: catch weaker detections to find target faster

# DIoU duplicate merge thresholds
# DIoU = IoU - (center_dist^2 / enclosing_diag^2)
# This metric considers BOTH overlap AND center distance, making it better
# than plain IoU for distinguishing true duplicates from nearby real objects.
DUPLICATE_DIOU_THRESHOLD = 0.30      # Strong duplicate: definitely merge
DUPLICATE_BORDERLINE_THRESHOLD = 0.10 # Below this: definitely NOT a duplicate
DUPLICATE_BORDERLINE_MIN_IOU = 0.25   # Borderline DIoU also needs decent IoU
DUPLICATE_BORDERLINE_CENTROID_FRACTION = 0.35 # And centroids must be close


class PerceptionSystem:
    """Main perception pipeline — processes one frame at a time.

    Who creates this: main.py creates a single instance at startup.
    Who calls process_frame(): webRTC.py (for live stream) and main.py (for single capture).

    The system maintains state across frames:
      - frame_id: monotonically increasing frame counter
      - first_seen: when each tracked object was first detected (for age calculation)
      - last_depth: the most recent depth map (from DepthUpdater)
      - last_spoken: the last search announcement (to avoid repeating)
    """

    def __init__(self, tracker, depth_provider):
        self.tracker = tracker              # ObjectTracker (YOLO + ByteTrack)
        self.depth_provider = depth_provider  # DepthUpdater (async MiDaS depth)

        self.frame_id = 0                   # Frame counter (incremented each frame)
        self.first_seen: Dict[str, float] = {}  # object_id → timestamp first detected
        self.last_depth = None              # Latest depth map (legacy, now uses depth_provider)

        self.last_spoken = ""               # Last search announcement text (dedup)

        # Performance metrics (exposed to frontend via perf_stats())
        self._last_infer_ms = 0.0           # Last YOLO inference time in ms
        self._fps = 0.0                     # Smoothed FPS estimate
        self._perf_last = None              # Timestamp of last perf_stats() call

    def perf_stats(self) -> dict:
        """Calculate current FPS and return performance metrics.
        Uses exponential moving average (EMA) for smooth FPS readings
        even when frames arrive in bursts (WebSocket decode + to_thread)."""
        now = time.time()
        if self._perf_last is not None:
            dt = now - self._perf_last
            if dt > 0.01:
                inst = 1.0 / dt  # Instantaneous FPS from frame delta
                # EMA smoothing: 80% old value + 20% new value
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
        """Process a single camera frame through the entire perception pipeline.

        Input:
            frame: OpenCV image (numpy array, BGR format, any resolution)

        Output:
            SystemEvent with event_type="PERCEPTION_FRAME_READY" containing:
              - TrackingState with active_objects (Dict[str, ObjectData])
              - frame_id, timestamp, perf stats, frame dimensions

        This method is called from a thread pool (asyncio.to_thread) to avoid
        blocking the async event loop. YOLO inference is CPU/GPU-bound.

        Complete flow:
            frame → YOLO tracking → depth read → object building
                → duplicate removal → search matching → event creation
        """
        start_total = time.time()
        timestamp = time.time()
        self.frame_id += 1

        h, w = frame.shape[:2]

        # =========================
        # STEP 1: OBJECT DETECTION + TRACKING
        # =========================
        conf = SEARCH_CONFIDENCE if SEARCH_TARGET else NORMAL_CONFIDENCE
        t1 = time.time()
        tracks, _ = self.tracker.track(frame, conf=conf)
        dt_detect = (time.time() - t1) * 1000
        self._last_infer_ms = dt_detect

        # =========================
        # STEP 2: DEPTH (ASYNC — NEVER BLOCKS DETECTION)
        # =========================
        t2 = time.time()
        if getattr(self.depth_provider, "feed", None) is not None:
            self.depth_provider.feed(frame)
        depth_map, depth_timestamp = self.depth_provider.current()

        if depth_map is not None and depth_timestamp is not None:
            depth_age = timestamp - depth_timestamp
            # Depth updates at ~600ms cadence. Allow up to 800ms stale depth
            # rather than discarding — a slightly old depth is better than none.
            if depth_age > 0.8:
                depth_map = None
        dt_depth = (time.time() - t2) * 1000

        # =========================
        # STEP 3: BUILD ENRICHED OBJECTS
        # =========================
        t3 = time.time()
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
        dt_build = (time.time() - t3) * 1000

        # =========================
        # STEP 4: REMOVE DUPLICATE DETECTIONS
        # =========================
        t4 = time.time()
        active_objects = self._dedupe_overlapping(active_objects)
        dt_dedupe = (time.time() - t4) * 1000

        # =========================
        # STEP 5: SEARCH MATCHING + SPEECH
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

        if len(search_matches) == 0:
            self.last_spoken = ""

        # =========================
        # STEP 6: CREATE SYSTEM EVENT
        # =========================
        state = TrackingState(
            active_objects=active_objects,
            frame_id=self.frame_id,
            timestamp=timestamp,
            perf=self.perf_stats(),
            frame_width=w,
            frame_height=h,
        )
        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type="PERCEPTION_FRAME_READY",
            payload=state,
            priority=1,
            timestamp=timestamp,
        )

        dt_total = (time.time() - start_total) * 1000

        # Log timing breakdown every 30 frames (~1 second at 30fps)
        if self.frame_id % 30 == 0:
            logger.info(
                f"[PERF] frame={self.frame_id} total={dt_total:.0f}ms "
                f"detect={dt_detect:.0f}ms depth_read={dt_depth:.1f}ms "
                f"build={dt_build:.1f}ms dedupe={dt_dedupe:.1f}ms "
                f"tracks={len(tracks)} objects={len(active_objects)} "
                f"matches={len(search_matches)} "
                f"frame_size={w}x{h}"
            )

        # Cleanup first_seen dict every 300 frames (~10s at 30fps) to prevent unbounded growth
        if self.frame_id % 300 == 0:
            cutoff = timestamp - 300.0  # Remove entries older than 5 minutes
            stale = [k for k, v in self.first_seen.items() if v < cutoff]
            for k in stale:
                del self.first_seen[k]
            if stale:
                logger.info(f"[PERF] Cleaned {len(stale)} stale first_seen entries")

        return event

    # =========================
    # DUPLICATE DETECTION MERGE
    # =========================
    @staticmethod
    def _iou(a, b):
        """Calculate Intersection over Union (IoU) between two bounding boxes.
        IoU = area of overlap / area of union.
        Used as part of the duplicate detection logic."""
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

    @staticmethod
    def _diou(a, b):
        """Distance-IoU: DIoU = IoU - (center_dist^2 / enclosing_diag^2).
        Better than plain IoU because it also penalizes center distance.
        Two boxes with high overlap but far apart centers get a lower DIoU,
        preventing incorrect merging of nearby real objects."""
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b

        a_area = (ax2 - ax1) * (ay2 - ay1)
        b_area = (bx2 - bx1) * (by2 - by1)
        if a_area <= 0 or b_area <= 0:
            return 0.0

        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)

        union = a_area + b_area - inter
        if union <= 0:
            return 0.0
        iou = inter / union

        # Center distance penalty
        acx, acy = (ax1 + ax2) / 2, (ay1 + ay2) / 2
        bcx, bcy = (bx1 + bx2) / 2, (by1 + by2) / 2
        center_dist2 = (acx - bcx) ** 2 + (acy - bcy) ** 2

        # Enclosing diagonal
        ex1, ey1 = min(ax1, bx1), min(ay1, by1)
        ex2, ey2 = max(ax2, bx2), max(ay2, by2)
        diag2 = (ex2 - ex1) ** 2 + (ey2 - ey1) ** 2

        if diag2 <= 0:
            return iou
        return iou - center_dist2 / diag2

    @staticmethod
    def _is_duplicate(a, b):
        """Two-stage duplicate decision:
        1. Strong DIoU (>= 0.30) → definitely a duplicate
        2. Borderline DIoU (0.10-0.30) → duplicate only if IoU is also decent
           AND centroids are close (prevents merging two nearby real objects)

        This is critical for avoiding false merges of two people standing
        next to each other, while still catching ghost/jitter duplicates.
        """
        diou = PerceptionSystem._diou(a, b)
        if diou >= DUPLICATE_DIOU_THRESHOLD:
            return True
        if diou < DUPLICATE_BORDERLINE_THRESHOLD:
            return False

        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        min_side = min(
            ax2 - ax1, ay2 - ay1, bx2 - bx1, by2 - by1
        )
        if min_side <= 0:
            return False

        # Check if centroids are close relative to the smaller box
        acx, acy = (ax1 + ax2) / 2, (ay1 + ay2) / 2
        bcx, bcy = (bx1 + bx2) / 2, (by1 + by2) / 2
        max_centroid2 = (DUPLICATE_BORDERLINE_CENTROID_FRACTION * min_side) ** 2
        if (acx - bcx) ** 2 + (acy - bcy) ** 2 > max_centroid2:
            return False

        return PerceptionSystem._iou(a, b) >= DUPLICATE_BORDERLINE_MIN_IOU

    def _dedupe_overlapping(self, active_objects):
        """Remove duplicate/ghost detections of the same class.
        When two boxes overlap heavily (split tracks from YOLO/ByteTrack),
        keep only the one with highest confidence.

        Input: dict of object_id → ObjectData
        Output: same dict with duplicates removed
        """
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
                if self._is_duplicate(obj.bbox, other.bbox):
                    # Keep the higher-confidence detection
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
        """Convert a raw Track into an enriched ObjectData.

        This adds:
          - Depth value from the MiDaS depth map
          - Horizontal offset (how far left/right from center)
          - Object ID for persistent tracking
          - First-seen timestamp for age calculation

        Input: Track from ObjectTracker, depth map, frame dimensions
        Output: ObjectData or None (if the box is degenerate)

        The ObjectData is what flows through the entire rest of the pipeline
        (ReasoningLayer, RuleEngine, WebSocket broadcast, etc.)
        """
        try:
            x1, y1, x2, y2 = map(int, track.bbox)

            # Clamp bounding box to frame boundaries
            x1 = max(0, min(x1, frame_width - 1))
            x2 = max(0, min(x2, frame_width - 1))
            y1 = max(0, min(y1, frame_height - 1))
            y2 = max(0, min(y2, frame_height - 1))

            # Skip degenerate boxes (zero area)
            if x2 <= x1 or y2 <= y1:
                return None

            # Calculate center point and horizontal offset
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            # Horizontal offset normalized to [-1, 1]: -1 = far left, +1 = far right
            horizontal_offset = (cx - frame_width / 2) / (frame_width / 2)
            horizontal_offset = float(np.clip(horizontal_offset, -1.0, 1.0))

            # Extract depth for this object's bounding box region
            if depth_map is not None:
                depth_norm, depth_conf = self._extract_depth(
                    depth_map, x1, y1, x2, y2
                )
            else:
                depth_norm, depth_conf = 0.0, 0.0

            object_id = f"track_{track.track_id}"

            # Record when this object was first seen (for age calculation)
            if object_id not in self.first_seen:
                self.first_seen[object_id] = timestamp

            return ObjectData(
                object_id=object_id,
                class_name=track.class_name,
                confidence=float(track.confidence),
                bbox=(x1, y1, x2, y2),
                centroid=(cx, cy),

                depth_norm=float(depth_norm),       # 0-1 normalized depth
                depth_confidence=float(depth_conf),  # 0 or 1 (simple confidence)

                horizontal_offset_norm=horizontal_offset,  # -1 to +1 (left to right)

                velocity_norm=None,          # Filled in by ReasoningLayer
                direction_vector=None,       # Filled in by ReasoningLayer
                is_stationary=False,         # Filled in by ReasoningLayer
                is_moving_towards_user=False, # Filled in by ReasoningLayer

                first_seen_ts=self.first_seen[object_id],
                last_seen_ts=timestamp,
                frame_timestamp=timestamp,

                track_id=int(track.track_id),  # ByteTrack's persistent ID
            )

        except Exception as e:
            logger.error(f"Object build error: {e}")
            return None

    # =========================
    # DEPTH EXTRACTOR
    # =========================
    def _extract_depth(self, depth_map, x1, y1, x2, y2):
        """Extract the average depth value for a bounding box region.

        Input: depth map (2D numpy array, normalized 0-1) and bbox coordinates
        Output: (depth_norm, depth_confidence) tuple

        The depth map comes from DepthUpdater which runs MiDaS asynchronously.
        We take the mean depth of all pixels within the bounding box,
        giving a rough distance estimate for the detected object.
        """
        region = depth_map[y1:y2, x1:x2]

        if region.size == 0:
            return 0.0, 0.0

        depth = float(np.mean(region))
        return depth, 1.0
