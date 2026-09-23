# =============================================================================
# FILE: App/core/reasoning_layer.py
# ROLE: Reasoning Layer — evaluates threats and builds the scene graph.
#
# WHAT THIS FILE DOES:
#   Takes raw tracking data from the Perception Layer and produces
#   higher-level understanding:
#   1. Computes velocity for each object (how fast it's approaching)
#   2. Evaluates threat levels (0-3) based on depth, velocity, alignment
#   3. Builds a scene graph with spatial relationships (left/right/ahead)
#   4. Publishes "FRAME_ANALYSIS_READY" event for the Rule Engine
#
# FLOW:
#   EventBus delivers "PERCEPTION_FRAME_READY" event
#       ↓
#   ReasoningLayer.handle_event()
#       ↓
#   _process_frame():
#       1. Update object history (depth, position over time)
#       2. Clean up stale objects (not seen for 3+ seconds)
#       3. Compute velocity for each object
#       4. Evaluate threat levels
#       5. Build scene graph (spatial relationships)
#       6. Publish "FRAME_ANALYSIS_READY" → EventBus → RuleEngine
#
# THREAT EVALUATION:
#   risk = W_PROXIMITY * proximity_score + W_VELOCITY * velocity_score + W_ALIGNMENT * alignment_score
#   Where:
#     - proximity_score: closer = higher risk
#     - velocity_score: faster approach = higher risk
#     - alignment_score: more centered = higher risk
#   Thresholds from safety.py determine threat level (0-3)
#
# WHO CALLS THIS:
#   EventBus calls handle_event() when "PERCEPTION_FRAME_READY" is published
#
# WHERE THE RESULT GOES:
#   Publishes "FRAME_ANALYSIS_READY" → EventBus → RuleEngine
# =============================================================================

# core/reasoning_layer.py
import logging
import time
import uuid
from collections import deque
from typing import Deque, Dict, List

from App.core.contracts import (
    ObjectData,
    TrackingState,
    ThreatAssessment,
    SceneGraph,
    SceneRelation,
    SystemEvent,
    FrameAnalysis,
)
from App.core.safety import (
    DEPTH_VERY_CLOSE,
    DEPTH_NEAR,
    VELOCITY_HIGH,
    VELOCITY_MED,
    W_PROXIMITY,
    W_VELOCITY,
    W_ALIGNMENT,
    RISK_LEVEL_0,
    RISK_LEVEL_1,
    RISK_LEVEL_2,
)

logger = logging.getLogger(__name__)

class ObjectSnapshot:
    """Lightweight snapshot of an object's state at a single point in time.
    Used to build a history of each object's depth and position over time,
    which is needed to compute velocity and detect approaching objects."""
    __slots__ = ("depth_norm", "horizontal_offset_norm", "timestamp")

    def __init__(self, depth_norm, horizontal_offset_norm, timestamp):
        self.depth_norm = depth_norm
        self.horizontal_offset_norm = horizontal_offset_norm
        self.timestamp = timestamp


class ReasoningLayer:
    """Evaluates threats and builds the scene graph from tracking data.

    Who creates this: main.py creates a single instance at startup.
    Who calls handle_event(): EventBus (when "PERCEPTION_FRAME_READY" is published).

    Maintains per-object history to compute velocity and detect approaching objects.
    """

    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.object_history: Dict[str, Deque[ObjectSnapshot]] = {}  # object_id → history
        self.active_objects: Dict[str, ObjectData] = {}  # Current frame's objects

        self.history_size = 5          # Keep last 5 snapshots per object
        self.history_ttl_sec = 3.0     # Remove objects not seen for 3+ seconds

    # ================= ENTRY POINT =================

    async def handle_event(self, event: SystemEvent) -> None:
        """Event handler — called by EventBus when "PERCEPTION_FRAME_READY" is published.

        Flow:
            Event arrives → extract TrackingState → _process_frame()
        """
        if event.event_type != "PERCEPTION_FRAME_READY":
            return

        tracking_state: TrackingState = event.payload
        await self._process_frame(tracking_state)

    # ================= MAIN PROCESSING =================

    async def _process_frame(self, tracking_state: TrackingState):
        """Process a complete frame's tracking data.

        Flow:
            1. Store current objects
            2. Clean up stale history (objects not seen recently)
            3. Update object history (for velocity computation)
            4. Evaluate threats for each object
            5. Build scene graph (spatial relationships)
            6. Publish "FRAME_ANALYSIS_READY" event
        """
        logger.info("\n[Reasoning] ===== NEW FRAME =====")

        # Log incoming objects for debugging
        for obj in tracking_state.active_objects.values():
            logger.info(
                f"[Reasoning][IN] {obj.object_id} | {obj.class_name} | "
                f"depth={obj.depth_norm:.2f} | offset={obj.horizontal_offset_norm:.2f}"
            )

        self.active_objects = tracking_state.active_objects
        logger.info(
            f"[Reasoning] FRAME {tracking_state.frame_id} "
            f"| objects={len(self.active_objects)}"
        )

        # Remove history for objects that haven't been seen recently
        self._cleanup_stale_history(tracking_state.timestamp)

        # Limit to 10 objects max to prevent performance issues
        MAX_OBJECTS = 10
        objects = list(self.active_objects.values())[:MAX_OBJECTS]

        # Record each object's state in history (for velocity computation)
        for obj in objects:
            self._update_object_history(obj)

        start = time.time()

        # Evaluate threat levels for all objects
        threats = await self._evaluate_threats()

        logger.debug(f"[PERF] reasoning={(time.time() - start) * 1000:.1f}ms")

        logger.info(f"[Reasoning][SUMMARY] threats={len(threats)}")

        # Build spatial relationship graph
        scene_graph = self._build_scene_graph()

        # Publish the combined analysis to the EventBus
        await self._emit_frame_analysis(
            tracking_state.frame_id,
            tracking_state.timestamp,
            scene_graph,
            threats,
        )

    # ================= OBJECT HISTORY =================

    def _update_object_history(self, obj: ObjectData):
        """Record an object's current state in its history buffer.
        Used to compute velocity over time (depth change / time delta)."""
        if obj.object_id not in self.object_history:
            self.object_history[obj.object_id] = deque(maxlen=self.history_size)

        self.object_history[obj.object_id].append(
            ObjectSnapshot(
                obj.depth_norm,
                obj.horizontal_offset_norm,
                obj.last_seen_ts or obj.frame_timestamp,
            )
        )

    def _cleanup_stale_history(self, current_ts: float):
        """Remove history for objects that haven't been seen recently.
        Prevents memory leaks and stale velocity calculations."""
        to_remove = []

        for oid, history in self.object_history.items():
            if history and current_ts - history[-1].timestamp > self.history_ttl_sec:
                to_remove.append(oid)

        for oid in to_remove:
            del self.object_history[oid]
            logger.info(f"[Reasoning] removed stale object {oid}")

    # ================= VELOCITY COMPUTATION =================

    def _compute_velocity(self, history: Deque[ObjectSnapshot]) -> float:
        """Compute the velocity of an object toward/away from the user.

        Uses the change in depth over time. Positive velocity = approaching,
        negative velocity = moving away.

        Flow:
            history = [snapshot1, snapshot2, ..., snapshotN]
                → compute dt and d_depth between consecutive snapshots
                → velocity = d_depth / dt (depth change per second)
                → median smoothing to reduce noise
                → clamp to [-3.0, 3.0] to prevent extreme values

        Requires at least 3 snapshots for meaningful computation.
        """
        if len(history) < 3:
            return 0.0

        velocities = []

        for i in range(1, len(history)):
            h1 = history[i - 1]
            h2 = history[i]

            dt = h2.timestamp - h1.timestamp
            if dt <= 0:
                continue

            # Positive velocity = depth decreasing = object approaching
            velocities.append((h1.depth_norm - h2.depth_norm) / dt)

        if not velocities:
            return 0.0

        # Median smoothing to reduce noise from depth estimation jitter
        velocities.sort()
        mid = len(velocities) // 2
        median = velocities[mid]

        # Ignore very small velocities (noise floor)
        if abs(median) < 0.01:
            return 0.0

        # Clamp extremes to prevent unreasonable values
        return max(min(median, 3.0), -3.0)

    def _compute_depth_thresholds(self):
        """Return the depth thresholds from safety.py."""
        return DEPTH_VERY_CLOSE, DEPTH_NEAR

    def _depth_to_bucket(self, depth):
        """Convert a normalized depth value to a human-readable bucket.
        Used for speech generation and threat assessment."""
        if depth >= DEPTH_VERY_CLOSE:
            return "very_close"
        elif depth >= DEPTH_NEAR:
            return "near"
        return "far"

    def _is_intercepting(self, history):
        """Check if an object is on an intercepting trajectory.

        An object is "intercepting" if over the last 3 snapshots:
        - Depth is monotonically decreasing (getting closer)
        - Horizontal offset is monotonically decreasing (centering on user)

        This catches objects that are moving toward the user's position,
        not just getting closer in depth.
        """
        if len(history) < 3:
            return False

        h1, h2, h3 = history[-3], history[-2], history[-1]

        return (
            h1.depth_norm > h2.depth_norm > h3.depth_norm and
            abs(h1.horizontal_offset_norm) > abs(h2.horizontal_offset_norm) > abs(h3.horizontal_offset_norm)
        )

    # ================= THREAT EVALUATION =================

    async def _evaluate_threats(self) -> List[ThreatAssessment]:
        """Evaluate threat levels for all active objects.

        For each object:
        1. Compute velocity from history
        2. Check if it's intercepting
        3. Calculate risk score (weighted sum of proximity, velocity, alignment)
        4. Map risk score to threat level (0-3)
        5. Apply override rules (very_close + fast = level 3)

        Only objects with threat_level > 0 produce a ThreatAssessment.
        """
        threats = []
        for obj in self.active_objects.values():

            history = self.object_history.get(obj.object_id)

            if not history or len(history) < 3:
                continue

            velocity = self._compute_velocity(history)
            intercept = self._is_intercepting(history)
            depth_bucket = self._depth_to_bucket(obj.depth_norm)
            obj.velocity_norm = velocity

            logger.info(
                f"[Reasoning][PROCESS] {obj.object_id} | "
                f"velocity={velocity:.2f} | bucket={depth_bucket}"
            )

            # Weighted risk score calculation
            proximity_score = max(0.0, min(obj.depth_norm, 1.0))
            velocity_score = min(abs(velocity) / 0.3, 1.0)
            alignment_score = 1.0 - min(abs(obj.horizontal_offset_norm), 1.0)

            risk = (
                    W_PROXIMITY * proximity_score +
                    W_VELOCITY * velocity_score +
                    W_ALIGNMENT * alignment_score
            )

            # Map risk score to threat level
            if risk < RISK_LEVEL_0:
                level = 0
            elif risk < RISK_LEVEL_1:
                level = 1
            elif risk < RISK_LEVEL_2:
                level = 2
            else:
                level = 3

            # Override rules from SRS: very close + fast/intercepting = level 3
            if depth_bucket == "very_close" and (velocity > VELOCITY_HIGH or intercept):
                level = 3

            elif depth_bucket == "near" and (velocity > VELOCITY_MED or intercept):
                level = max(level, 2)

            if level == 0:
                continue  # Safe objects don't produce a threat assessment

            threat = ThreatAssessment(
                object_id=obj.object_id,
                class_name=obj.class_name,
                depth_norm=obj.depth_norm,
                velocity_norm=velocity,
                threat_level=level,
                reason="intercepting" if intercept else ("approaching" if velocity > 0 else "close"),
                priority=0 if level == 3 else (1 if level == 2 else 2),
                timestamp=time.time(),
                horizontal_offset_norm=obj.horizontal_offset_norm,
                depth_bucket=depth_bucket,
            )

            logger.info(
                f"[Reasoning][OUT] {obj.object_id} | class={obj.class_name} | "
                f"level={level} | velocity={velocity:.2f} | {depth_bucket}"
            )

            threats.append(threat)

        return threats

    # ================= SCENE GRAPH =================

    def _build_scene_graph(self) -> SceneGraph:
        """Build a spatial relationship graph for the current frame.

        Creates a virtual "USER" object representing the camera/user position,
        then computes spatial relationships (left/right/ahead, distance) between
        each detected object and the user.

        The scene graph is used by the RuleEngine to generate navigation
        speech (e.g. "person on your left, nearby").
        """
        relations = []

        # Virtual object representing the user/camera position
        user_object = ObjectData(
            object_id="USER",
            class_name="user",
            confidence=1.0,
            bbox=(0, 0, 0, 0),
            centroid=(0, 0),
            depth_norm=1.0,
            depth_confidence=1.0,
            horizontal_offset_norm=0.0,
        )

        objects = dict(self.active_objects)
        objects["USER"] = user_object

        for obj in self.active_objects.values():
            # Determine left/right/ahead based on horizontal offset
            direction = (
                "left" if obj.horizontal_offset_norm < -0.25
                else "right" if obj.horizontal_offset_norm > 0.25
                else "ahead"
            )

            # Add directional relation (e.g. "track_1 is left of USER")
            relations.append(SceneRelation(obj.object_id, direction, "USER", 0.9))
            # Add distance relation (e.g. "track_1 is very_close to USER")
            relations.append(
                SceneRelation(
                    obj.object_id,
                    self._depth_to_bucket(obj.depth_norm),
                    "USER",
                    0.8
                )
            )

        return SceneGraph(objects=objects, relations=relations, timestamp=time.time())

    # ================= EMIT TO EVENT BUS =================

    async def _emit_frame_analysis(self, frame_id, timestamp, scene_graph, threats):
        """Package the analysis results and publish to the EventBus.

        Flow:
            FrameAnalysis (scene_graph + threats)
                → SystemEvent("FRAME_ANALYSIS_READY")
                    → EventBus → RuleEngine.handle_event()
        """
        logger.info("[Reasoning] EMIT -> FRAME_ANALYSIS_READY")

        await self.event_bus.publish(
            SystemEvent(
                event_id=str(uuid.uuid4()),
                event_type="FRAME_ANALYSIS_READY",
                payload=FrameAnalysis(
                    frame_id=frame_id,
                    timestamp=timestamp,
                    scene_graph=scene_graph,
                    threats=threats,
                ),
                priority=1,
                timestamp=time.time(),
            )
        )
