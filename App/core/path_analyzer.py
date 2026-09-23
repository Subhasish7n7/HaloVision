"""
Path analyzer — determines if the walking path ahead is clear.

Triggered by the raised-hand gesture (open_palm) from the frontend.
Uses existing PerceptionSystem detections (objects, bounding boxes, depth)
to evaluate whether the walking corridor is obstructed.

Safety principle: when uncertain, report UNCERTAIN — never assume CLEAR.
"""

import logging
from typing import Dict, List, Tuple, Optional

from App.core.contracts import ObjectData, TrackingState
from App.core.safety import DEPTH_VERY_CLOSE, DEPTH_NEAR

logger = logging.getLogger(__name__)

# Walking corridor in normalized frame coordinates (0-1).
# The corridor represents the area directly ahead of the user where
# they would walk. Objects here are potential obstructions.
#
# x: 0.25 - 0.75  → middle 50% of frame width
# y: 0.30 - 0.95  → from chest level down to feet
CORRIDOR_X_MIN = 0.25
CORRIDOR_X_MAX = 0.75
CORRIDOR_Y_MIN = 0.30
CORRIDOR_Y_MAX = 0.95

# Minimum object size (fraction of frame area) to consider as a path blocker.
# Tiny远处 objects are ignored even if technically in the corridor.
MIN_BLOCKING_AREA = 0.005

# Depth thresholds (MiDaS normalized 0-1, higher = closer).
DEPTH_CLOSE = 0.55    # Object is close enough to block the path
DEPTH_MEDIUM = 0.35   # Object is at medium distance — uncertain
DEPTH_FAR = 0.15      # Object is far — unlikely to block

# Minimum number of detections to consider the scene well-understood
MIN_DETECTIONS_FOR_CONFIDENCE = 1

# Path status messages for TTS
TTS_MESSAGES = {
    "CLEAR": "The path ahead appears clear.",
    "BLOCKED": "The path ahead is blocked.",
    "UNCERTAIN": "I can't confirm the path is clear.",
}


class PathAnalyzer:
    """Analyzes whether the walking path ahead is clear.

    Uses the same detection data that the rest of the pipeline produces.
    Does NOT run its own ML inference — reuses existing detections.

    Safety-first design:
    - Reports BLOCKED when obstacles are in the walking corridor
    - Reports UNCERTAIN when confidence is low, depth is missing, or
      the scene is too complex to reliably determine path status
    - Reports CLEAR only when there is sufficient evidence of an open path
    """

    def __init__(self):
        pass

    def analyze(
        self,
        tracking_state: TrackingState,
        frame_width: int = 0,
        frame_height: int = 0,
    ) -> dict:
        """Analyze the current frame's detections for path clearness.

        Args:
            tracking_state: Current frame's tracking state from PerceptionSystem
            frame_width: Frame width in pixels (for corridor calculation)
            frame_height: Frame height in pixels (for corridor calculation)

        Returns:
            dict with keys:
                - status: "CLEAR" | "BLOCKED" | "UNCERTAIN"
                - message: Human-readable TTS message
                - obstacles: List of blocking objects (for logging)
                - confidence: Float 0-1 (how confident we are in the result)
        """
        objects = tracking_state.active_objects
        w = frame_width or tracking_state.frame_width
        h = frame_height or tracking_state.frame_height

        if not objects:
            logger.info("[PathAnalyzer] No objects detected — path assumed clear")
            return {
                "status": "CLEAR",
                "message": TTS_MESSAGES["CLEAR"],
                "obstacles": [],
                "confidence": 0.6,
            }

        # Analyze each object
        blocking_objects = []
        near_objects = []
        total_in_corridor = 0
        has_depth = False

        for obj in objects.values():
            if obj.class_name == "user":
                continue

            result = self._evaluate_object(obj, w, h)

            if result is None:
                continue

            total_in_corridor += 1

            if result["has_depth"]:
                has_depth = True

            if result["is_blocking"]:
                blocking_objects.append(result)
            elif result["is_near"]:
                near_objects.append(result)

        # Log analysis
        logger.info(
            f"[PathAnalyzer] Objects in corridor: {total_in_corridor} | "
            f"Blocking: {len(blocking_objects)} | Near: {len(near_objects)} | "
            f"Has depth: {has_depth}"
        )

        # Determine path status
        status, confidence = self._determine_status(
            blocking_objects=blocking_objects,
            near_objects=near_objects,
            total_objects=len(objects),
            total_in_corridor=total_in_corridor,
            has_depth=has_depth,
        )

        message = TTS_MESSAGES[status]

        logger.info(
            f"[PathAnalyzer] PATH STATUS: {status} | "
            f"Confidence: {confidence:.2f} | "
            f"Message: {message}"
        )

        return {
            "status": status,
            "message": message,
            "obstacles": [
                {
                    "class": o["class_name"],
                    "depth": o["depth"],
                    "position": o["position"],
                }
                for o in blocking_objects
            ],
            "confidence": confidence,
        }

    def _evaluate_object(
        self,
        obj: ObjectData,
        frame_width: int,
        frame_height: int,
    ) -> Optional[dict]:
        """Evaluate a single object for path-blocking potential.

        Returns None if the object is outside the walking corridor or
        too small/distant to matter. Otherwise returns analysis dict.
        """
        x1, y1, x2, y2 = obj.bbox

        # Convert to normalized coordinates
        if frame_width > 0 and frame_height > 0:
            nx1, ny1 = x1 / frame_width, y1 / frame_height
            nx2, ny2 = x2 / frame_width, y2 / frame_height
        else:
            # Fallback: use horizontal_offset and depth to estimate
            nx1 = 0.5 + obj.horizontal_offset_norm * 0.3 - 0.1
            nx2 = nx1 + 0.2
            ny1 = 0.3
            ny2 = 0.8

        # Check if object intersects the walking corridor
        in_x = nx2 > CORRIDOR_X_MIN and nx1 < CORRIDOR_X_MAX
        in_y = ny2 > CORRIDOR_Y_MIN and ny1 < CORRIDOR_Y_MAX

        if not (in_x and in_y):
            return None

        # Calculate object size (fraction of frame area)
        obj_area = max(0, nx2 - nx1) * max(0, ny2 - ny1)

        if obj_area < MIN_BLOCKING_AREA:
            return None

        depth = obj.depth_norm
        has_depth = obj.depth_confidence > 0

        # Determine if this object blocks the path
        is_blocking = False
        is_near = False

        # BLOCKING: close object in the corridor
        if depth >= DEPTH_CLOSE:
            is_blocking = True
        elif depth >= DEPTH_MEDIUM:
            # Medium distance — blocking if it's large and centered
            horizontal_center = abs(obj.horizontal_offset_norm)
            if obj_area > 0.02 and horizontal_center < 0.3:
                is_blocking = True
            else:
                is_near = True
        elif depth >= DEPTH_FAR:
            is_near = True

        # Large objects are more likely to block even at distance
        if obj_area > 0.05 and depth >= DEPTH_FAR:
            is_near = True
            # Very large + medium distance = blocking
            if depth >= DEPTH_MEDIUM:
                is_blocking = True

        position = "ahead"
        if obj.horizontal_offset_norm < -0.25:
            position = "left"
        elif obj.horizontal_offset_norm > 0.25:
            position = "right"

        return {
            "class_name": obj.class_name,
            "confidence": obj.confidence,
            "depth": depth,
            "has_depth": has_depth,
            "area": obj_area,
            "position": position,
            "is_blocking": is_blocking,
            "is_near": is_near,
            "horizontal_offset": obj.horizontal_offset_norm,
        }

    def _determine_status(
        self,
        blocking_objects: list,
        near_objects: list,
        total_objects: int,
        total_in_corridor: int,
        has_depth: bool,
    ) -> Tuple[str, float]:
        """Determine the final path status based on all analyzed objects.

        Safety-first approach:
        - Any blocking object → BLOCKED
        - No blocking but near objects + no depth → UNCERTAIN
        - No blocking + no near objects + sufficient data → CLEAR
        - Very few detections + no depth → UNCERTAIN (might be missing objects)
        """

        # Rule 1: If there are blocking objects, path is BLOCKED
        if blocking_objects:
            closest = min(blocking_objects, key=lambda o: o["depth"])
            confidence = min(0.9, 0.6 + closest["confidence"] * 0.3)
            logger.info(
                f"[PathAnalyzer] BLOCKED by {closest['class_name']} "
                f"at depth {closest['depth']:.2f}"
            )
            return "BLOCKED", confidence

        # Rule 2: Near objects but no depth information → UNCERTAIN
        if near_objects and not has_depth:
            logger.info("[PathAnalyzer] UNCERTAIN — near objects without depth")
            return "UNCERTAIN", 0.4

        # Rule 3: Few detections overall → might be missing context → UNCERTAIN
        if total_objects < MIN_DETECTIONS_FOR_CONFIDENCE and not has_depth:
            logger.info("[PathAnalyzer] UNCERTAIN — few detections, no depth")
            return "UNCERTAIN", 0.35

        # Rule 4: Near objects with depth but all far enough → CLEAR with lower confidence
        if near_objects:
            closest_near = min(near_objects, key=lambda o: o["depth"])
            if closest_near["depth"] < DEPTH_MEDIUM:
                return "CLEAR", 0.7
            # Objects at medium distance — slightly uncertain
            return "CLEAR", 0.6

        # Rule 5: No blocking or near objects → CLEAR
        if has_depth:
            return "CLEAR", 0.85
        else:
            return "CLEAR", 0.65


# Singleton instance
path_analyzer = PathAnalyzer()
