# core/reasoning_layer.py

import logging
import time
import uuid
from collections import deque
from typing import Deque, Dict, Optional, List

from App.core.contracts import (
    ObjectData,
    TrackingState,
    ThreatAssessment,
    SceneGraph,
    SceneRelation,
    SystemEvent,
    FrameAnalysis,   # NEW
)

logger = logging.getLogger(__name__)


class ObjectSnapshot:
    __slots__ = ("depth_m", "horizontal_offset_norm", "timestamp")

    def __init__(self, depth_m, horizontal_offset_norm, timestamp):
        self.depth_m = depth_m
        self.horizontal_offset_norm = horizontal_offset_norm
        self.timestamp = timestamp


class ReasoningLayer:

    def __init__(self, event_bus) -> None:
        self.event_bus = event_bus

        self.object_history: Dict[str, Deque[ObjectSnapshot]] = {}
        self.active_objects: Dict[str, ObjectData] = {}

        self.history_size = 5
        self.history_ttl_sec = 3.0


    # ============================================================

    async def handle_event(self, event: SystemEvent) -> None:
        if event.event_type != "PERCEPTION_FRAME_READY":
            return

        tracking_state: TrackingState = event.payload
        await self._process_frame(tracking_state)

    async def _process_frame(self, tracking_state: TrackingState) -> None:
        logger.info(
            f"[Reasoning] Processing frame {tracking_state.frame_id} "
            f"with {len(tracking_state.active_objects)} objects"
        )

        self.active_objects = tracking_state.active_objects
        self._cleanup_stale_history(tracking_state.timestamp)
        logger.info(
            f"[Reasoning] FRAME {tracking_state.frame_id} "
            f"| objects={len(self.active_objects)}"
        )

        for obj in self.active_objects.values():
            self._update_object_history(obj)

        # ✅ COLLECT threats instead of emitting
        threats = await self._evaluate_threats()
        logger.info(f"[Reasoning] THREATS FOUND: {len(threats)}")

        scene_graph = self._build_scene_graph()
        logger.info(
            f"[Reasoning] EMIT FRAME_ANALYSIS_READY "
            f"| frame={tracking_state.frame_id} "
            f"| threats={len(threats)}"
        )

        # ✅ SINGLE EMIT
        await self._emit_frame_analysis(
            tracking_state.frame_id,
            tracking_state.timestamp,
            scene_graph,
            threats,
        )

    # ============================================================
    # HISTORY (UNCHANGED)
    # ============================================================

    def _update_object_history(self, obj: ObjectData) -> None:
        if obj.object_id not in self.object_history:
            self.object_history[obj.object_id] = deque(maxlen=self.history_size)

        self.object_history[obj.object_id].append(
            ObjectSnapshot(
                obj.depth_m,
                obj.horizontal_offset_norm,
                obj.last_seen_ts or obj.frame_timestamp,
            )
        )

    def _cleanup_stale_history(self, current_ts: float) -> None:
        to_remove = []

        for oid, history in self.object_history.items():
            if history and current_ts - history[-1].timestamp > self.history_ttl_sec:
                to_remove.append(oid)

        for oid in to_remove:
            del self.object_history[oid]
            logger.info(f"[Reasoning] Removed stale object {oid}")

    # ============================================================

    def _depth_to_bucket(self, depth: float) -> str:
        if depth < 1.0:
            return "very_close"
        elif depth < 2.5:
            return "near"
        return "far"

    def _compute_velocity(self, history: Deque[ObjectSnapshot]) -> float:
        if len(history) < 3:
            return 0.0

        velocities = []

        for i in range(1, len(history)):
            h1 = history[i - 1]
            h2 = history[i]

            dt = h2.timestamp - h1.timestamp
            if dt <= 0:
                continue

            velocities.append((h1.depth_m - h2.depth_m) / dt)

        if not velocities:
            return 0.0

        # 🔧 median smoothing (prevents spikes)
        velocities.sort()
        mid = len(velocities) // 2
        median = velocities[mid]

        # 🔧 ignore tiny noise
        if abs(median) < 0.05:
            return 0.0

        # 🔧 clamp extreme values
        return max(min(median, 3.0), -3.0)

    def _is_intercepting(self, history: Deque[ObjectSnapshot]) -> bool:
        if len(history) < 3:
            return False

        h1, h2, h3 = history[-3], history[-2], history[-1]

        return (
            h1.depth_m > h2.depth_m > h3.depth_m and
            abs(h1.horizontal_offset_norm) > abs(h2.horizontal_offset_norm) > abs(h3.horizontal_offset_norm)
        )

    def _compute_ttc(self, depth: float, velocity: float) -> Optional[float]:
        if velocity <= 0:
            return None
        return depth / velocity

    # ============================================================
    # 🔥 MODIFIED: now RETURNS list
    # ============================================================

    async def _evaluate_threats(self) -> List[ThreatAssessment]:
        threats: List[ThreatAssessment] = []

        for obj in self.active_objects.values():

            history = self.object_history.get(obj.object_id)
            if not history or len(history) < 2:
                continue

            velocity = self._compute_velocity(history)
            intercept = self._is_intercepting(history)
            depth_bucket = self._depth_to_bucket(obj.depth_m)
            obj.velocity_mps = velocity

            proximity_score = max(0.0, 1.0 - min(obj.depth_m / 3.0, 1.0))
            velocity_score = min(abs(velocity) / 2.0, 1.0)
            alignment_score = 1.0 - min(abs(obj.horizontal_offset_norm), 1.0)

            risk_score = (
                0.5 * proximity_score +
                0.3 * velocity_score +
                0.2 * alignment_score
            )

            if risk_score < 0.15:
                threat_level = 0
            elif risk_score < 0.35:
                threat_level = 1
            elif risk_score < 0.6:
                threat_level = 2
            else:
                threat_level = 3

            if depth_bucket == "very_close" and (velocity > 0.3 or intercept):
                threat_level = 3
            elif depth_bucket == "near" and (velocity > 0.2 or intercept):
                threat_level = max(threat_level, 2)

            if threat_level == 0:
                continue

            ttc = self._compute_ttc(obj.depth_m, velocity)

            assessment = ThreatAssessment(
                object_id=obj.object_id,
                class_name=obj.class_name,
                threat_level=threat_level,
                reason="intercepting" if intercept else ("approaching" if velocity > 0 else "close"),
                distance_m=obj.depth_m,
                time_to_collision=ttc,
                priority=0 if threat_level == 3 else (1 if threat_level == 2 else 2),
                timestamp=time.time(),
                horizontal_offset_norm=obj.horizontal_offset_norm,
                depth_bucket=depth_bucket,
                velocity_mps=velocity,
            )

            logger.info(
                f"[Reasoning] THREAT -> {obj.object_id} | level={threat_level} "
                f"| dist={depth_bucket}"
            )

            threats.append(assessment)

        return threats

    # ============================================================

    def _build_scene_graph(self) -> SceneGraph:
        relations = []

        user_object = ObjectData(
            object_id="USER",
            class_name="user",
            confidence=1.0,
            bbox=(0, 0, 0, 0),
            centroid=(0, 0),
            depth_m=0.0,
            depth_confidence=1.0,
            horizontal_offset_norm=0.0,
        )

        objects = dict(self.active_objects)
        objects["USER"] = user_object

        for obj in self.active_objects.values():

            direction = (
                "left" if obj.horizontal_offset_norm < -0.25
                else "right" if obj.horizontal_offset_norm > 0.25
                else "ahead"
            )

            relations.append(SceneRelation(obj.object_id, direction, "USER", 0.9))
            relations.append(SceneRelation(obj.object_id, self._depth_to_bucket(obj.depth_m), "USER", 0.8))

        return SceneGraph(objects=objects, relations=relations, timestamp=time.time())

    # ============================================================
    # 🔥 NEW EMIT
    # ============================================================

    async def _emit_frame_analysis(self, frame_id, timestamp, scene_graph, threats):
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
