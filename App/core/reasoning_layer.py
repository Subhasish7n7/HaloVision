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

logger = logging.getLogger()


class ObjectSnapshot:
    __slots__ = ("depth_norm", "horizontal_offset_norm", "timestamp")

    def __init__(self, depth_norm, horizontal_offset_norm, timestamp):
        self.depth_norm = depth_norm
        self.horizontal_offset_norm = horizontal_offset_norm
        self.timestamp = timestamp


class ReasoningLayer:

    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.object_history: Dict[str, Deque[ObjectSnapshot]] = {}
        self.active_objects: Dict[str, ObjectData] = {}

        self.history_size = 5
        self.history_ttl_sec = 3.0

    # ================= ENTRY =================

    async def handle_event(self, event: SystemEvent):
        if event.event_type != "PERCEPTION_FRAME_READY":
            return

        tracking_state: TrackingState = event.payload
        await self._process_frame(tracking_state)

    # ================= MAIN =================

    async def _process_frame(self, tracking_state: TrackingState):

        logger.info("\n[Reasoning] ===== NEW FRAME =====")

        # 🔥 INPUT LOG
        for obj in tracking_state.active_objects.values():
            logger.info(
                f"[Reasoning][IN] {obj.object_id} | {obj.class_name} | "
                f"depth={obj.depth_norm:.2f} | offset={obj.horizontal_offset_norm:.2f}"
            )

        self.active_objects = tracking_state.active_objects

        self._cleanup_stale_history(tracking_state.timestamp)

        for obj in self.active_objects.values():
            self._update_object_history(obj)

        threats = await self._evaluate_threats()

        logger.info(f"[Reasoning][SUMMARY] threats={len(threats)}")

        scene_graph = self._build_scene_graph()

        await self._emit_frame_analysis(
            tracking_state.frame_id,
            tracking_state.timestamp,
            scene_graph,
            threats,
        )

    # ================= HISTORY =================

    def _update_object_history(self, obj: ObjectData):
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
        to_remove = []

        for oid, history in self.object_history.items():
            if history and current_ts - history[-1].timestamp > self.history_ttl_sec:
                to_remove.append(oid)

        for oid in to_remove:
            del self.object_history[oid]
            logger.info(f"[Reasoning] removed stale object {oid}")

    # ================= CALCULATIONS =================

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

            velocities.append((h1.depth_norm - h2.depth_norm) / dt)

        if not velocities:
            return 0.0

        velocities.sort()
        return velocities[len(velocities) // 2]

    def _compute_depth_thresholds(self):
        values = [obj.depth_norm for obj in self.active_objects.values()]

        if len(values) < 3:
            return 0.7, 0.3

        values = sorted(values)
        n = len(values)

        return values[int(0.7 * n)], values[int(0.3 * n)]

    def _depth_to_bucket(self, depth, near_th, far_th):
        if depth >= near_th:
            return "very_close"
        elif depth >= far_th:
            return "near"
        return "far"

    def _is_intercepting(self, history):
        if len(history) < 3:
            return False

        h1, h2, h3 = history[-3], history[-2], history[-1]

        return (
            h1.depth_norm > h2.depth_norm > h3.depth_norm and
            abs(h1.horizontal_offset_norm) > abs(h2.horizontal_offset_norm) > abs(h3.horizontal_offset_norm)
        )

    # ================= THREATS =================

    async def _evaluate_threats(self) -> List[ThreatAssessment]:

        threats = []
        near_th, far_th = self._compute_depth_thresholds()

        for obj in self.active_objects.values():

            history = self.object_history.get(obj.object_id)

            if not history or len(history) < 3:
                continue

            velocity = self._compute_velocity(history)
            intercept = self._is_intercepting(history)
            depth_bucket = self._depth_to_bucket(obj.depth_norm, near_th, far_th)

            obj.velocity_norm = velocity

            # 🔥 PROCESS LOG
            logger.info(
                f"[Reasoning][PROCESS] {obj.object_id} | "
                f"velocity={velocity:.2f} | bucket={depth_bucket}"
            )

            # risk logic
            proximity = obj.depth_norm
            velocity_score = min(abs(velocity) / 0.3, 1.0)
            alignment = 1.0 - min(abs(obj.horizontal_offset_norm), 1.0)

            risk = 0.5 * proximity + 0.3 * velocity_score + 0.2 * alignment

            if risk < 0.15:
                level = 0
            elif risk < 0.35:
                level = 1
            elif risk < 0.6:
                level = 2
            else:
                level = 3

            if depth_bucket == "very_close" and (velocity > 0.05 or intercept):
                level = 3

            if level == 0:
                continue

            threat = ThreatAssessment(
                object_id=obj.object_id,
                class_name=obj.class_name,
                depth_norm=obj.depth_norm,
                velocity_norm=velocity,
                threat_level=level,
                reason="intercepting" if intercept else "approaching",
                priority=0 if level == 3 else 1,
                timestamp=time.time(),
                horizontal_offset_norm=obj.horizontal_offset_norm,
                depth_bucket=depth_bucket,
            )

            # 🔥 OUTPUT LOG
            logger.info(
                f"[Reasoning][OUT] {obj.object_id} | class={obj.class_name} | "
                f"level={level} | velocity={velocity:.2f} | {depth_bucket}"
            )

            threats.append(threat)

        return threats

    # ================= SCENE =================

    def _build_scene_graph(self):
        return SceneGraph(objects=self.active_objects, relations=[], timestamp=time.time())

    # ================= EMIT =================

    async def _emit_frame_analysis(self, frame_id, timestamp, scene_graph, threats):
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