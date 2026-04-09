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
    FrameAnalysis,
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
        print("✅ ReasoningLayer RECEIVED:", event.event_type)

        if event.event_type != "PERCEPTION_FRAME_READY":
            return

        tracking_state: TrackingState = event.payload
        await self._process_frame(tracking_state)

    # ============================================================

    async def _process_frame(self, tracking_state: TrackingState) -> None:
        self.active_objects = tracking_state.active_objects
        self._cleanup_stale_history(tracking_state.timestamp)

        for obj in self.active_objects.values():
            self._update_object_history(obj)

        threats = await self._evaluate_threats()
        scene_graph = self._build_scene_graph()

        # 🔍 DEBUG
        print("\n📊 REASONING OUTPUT")

        if not threats:
            print("No threats detected")

        for t in threats:
            print(
                f"{t.class_name} | Level={t.threat_level} | "
                f"Dist={t.distance_m:.2f}m | Vel={t.velocity_mps:.2f}"
            )

        await self._emit_frame_analysis(
            tracking_state.frame_id,
            tracking_state.timestamp,
            scene_graph,
            threats,
        )

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

    # ============================================================

    def _depth_to_bucket(self, depth: float) -> str:
        if depth < 1.2:
            return "very_close"
        elif depth < 2.5:
            return "near"
        return "far"

    # ============================================================

    async def _evaluate_threats(self) -> List[ThreatAssessment]:
        threats: List[ThreatAssessment] = []

        for obj in self.active_objects.values():

            history = self.object_history.get(obj.object_id)
            if not history:
                continue

            # 🔥 USE YOUR SPEED (from perception)
            velocity = obj.velocity_mps if obj.velocity_mps else 0.0

            depth_bucket = self._depth_to_bucket(obj.depth_m)

            # 🔥 ONLY CARE ABOUT APPROACHING OBJECTS
            if velocity < 0.1:
                continue

            # 🔥 FORCE THREAT IF CLOSE + MOVING
            if obj.depth_m < 2.0 and velocity > 0.15:
                threat_level = 2
            elif obj.depth_m < 1.2:
                threat_level = 3
            else:
                threat_level = 1

            assessment = ThreatAssessment(
                object_id=obj.object_id,
                class_name=obj.class_name,
                threat_level=threat_level,
                reason="approaching",
                distance_m=obj.depth_m,
                time_to_collision=(obj.depth_m / velocity) if velocity > 0 else None,
                priority=0 if threat_level >= 2 else 1,
                timestamp=time.time(),
                horizontal_offset_norm=obj.horizontal_offset_norm,
                depth_bucket=depth_bucket,
                velocity_mps=velocity,
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

    async def _emit_frame_analysis(self, frame_id, timestamp, scene_graph, threats):
        print("🚀 Emitting FRAME_ANALYSIS_READY")

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