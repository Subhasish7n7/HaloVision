# core/rule_engine.py

import time
import uuid
from typing import Dict
from collections import defaultdict
import logging

from App.core.contracts import (
    SystemEvent,
    FrameAnalysis,   # NEW
    SpeechIntent,
    ModeState,
)

logger = logging.getLogger(__name__)


class RuleEngine:

    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.mode_state = ModeState()

        self.last_spoken_key = None
        self.last_spoken_ts = 0.0
        self.duplicate_window_sec = 2.5

        self.object_last_announced: Dict[str, float] = {}
        self.cooldown_sec = 3.5

        self.last_search_ts = 0
        self.search_interval = 0.8
        self.latest_frame_ts = 0
        self.last_nav_ts = 0.0
        self.nav_interval = 1.5
        self.last_no_threat_ts = 0
        self.no_threat_interval = 3.0


    # ============================================================

    # async def handle_event(self, event: SystemEvent):
    #
    #     if event.event_type == "FRAME_ANALYSIS_READY":
    #         await self._handle_frame(event.payload)
    #
    #     elif event.event_type == "USER_COMMAND_RECEIVED":
    #         await self._handle_command(event.payload)
    #
    #     elif event.event_type == "MODE_CHANGED":
    #         self.mode_state = event.payload

    async def handle_event(self, event: SystemEvent):

        print("\n🧠 [RuleEngine] EVENT RECEIVED:", event.event_type)

        if event.event_type == "FRAME_ANALYSIS_READY":
            frame = event.payload

            print(f"[RuleEngine] Frame={frame.frame_id} | threats={len(frame.threats)}")

            await self._handle_frame(frame)

        elif event.event_type == "USER_COMMAND_RECEIVED":
            print("[RuleEngine] Command received")
            await self._handle_command(event.payload)

        elif event.event_type == "MODE_CHANGED":
            print("[RuleEngine] Mode updated")
            self.mode_state = event.payload

    # ============================================================
    # 🔥 NEW CORE HANDLER
    # ============================================================
    print("🔥 RULE ENGINE RECEIVED FRAME")
    async def _handle_frame(self, frame: FrameAnalysis):
        logger.info(f"[Rule] FRAME {frame.frame_id} | threats={len(frame.threats)}")

        print("\n========== RULE ENGINE ==========")

        print(f"[RULE-IN] Frame: {frame.frame_id}")
        print(f"[RULE-IN] Total threats: {len(frame.threats)}")

        for t in frame.threats:
            print(
                f"[RULE-IN] {t.object_id} | {t.class_name} | "
                f"level={t.threat_level} | depth={t.depth_bucket} | "
                f"velocity={t.velocity_norm:.2f}"
            )

        if frame.timestamp < self.latest_frame_ts:
            return

        self.latest_frame_ts = frame.timestamp

        scene = frame.scene_graph
        threats = frame.threats

        # ✅ store threats for nav filtering
        self._last_frame_threats = threats
        print(f"Threats: {len(frame.threats)}")
        # 1️⃣THREATS FIRST (priority)
        has_high_priority_threat = any(t.threat_level >= 2 for t in threats)

        for threat in threats:
            await self._handle_threat(threat)

        if self.mode_state.threat_mode:
            now = frame.timestamp

            if not threats and now - self.last_no_threat_ts > self.no_threat_interval:
                self.last_no_threat_ts = now

                await self._emit(
                    self._create_intent("threat", "No threats nearby", 1, None, 2.0)
                )
            return

        # 🚫 skip nav if threat is important
        if has_high_priority_threat:
            return

        # 2️⃣ SCENE LOGIC
        if self.mode_state.search_mode:
            await self._handle_search(scene)
            return

        if self.mode_state.description_mode:
            return

        await self._handle_navigation(scene)

    # ============================================================
    # EVERYTHING BELOW = UNCHANGED
    # ============================================================

    def _extract_relations(self, scene):
        rel_map = defaultdict(set)
        for rel in scene.relations:
            if rel.object_id == "USER":
                rel_map[rel.subject_id].add(rel.relation_type)
        return rel_map

    def _pluralize(self, word):
        if word == "person":
            return "people"
        if word.endswith(("s", "x", "z", "ch", "sh")):
            return word + "es"
        return word + "s"

    async def _handle_navigation(self, scene):
        now = scene.timestamp  # ✅ use frame time (NOT time.time())

        if now - self.last_nav_ts < self.nav_interval:
            return

        self.last_nav_ts = now

        relations = self._extract_relations(scene)

        # ✅ filter out objects already handled as threats
        threat_ids = {
            t.object_id
            for t in getattr(self, "_last_frame_threats", [])
            if t.threat_level >= 2
        }

        grouped = defaultdict(list)

        for obj in scene.objects.values():

            if obj.object_id == "USER":
                continue

            if obj.object_id in threat_ids:
                continue  # ✅ avoid duplicate speech

            if obj.confidence < 0.5:
                continue

            # ✅ improved far suppression logic
            is_approaching = obj.velocity_norm and obj.velocity_norm > 0

            if obj.depth_norm < 0.3 and not is_approaching:
                continue

            rels = relations.get(obj.object_id, set())

            direction = (
                "on your left" if "left" in rels
                else "on your right" if "right" in rels
                else "ahead"
            )

            distance = (
                "very close" if "very_close" in rels
                else "near you" if "near" in rels
                else "far away"
            )

            grouped[(obj.class_name, direction, distance)].append(obj)

        phrases = []

        sorted_groups = sorted(
            grouped.items(),
            key=lambda item: -max(o.depth_norm for o in item[1])
        )

        for (cls, direction, distance), objs in sorted_groups:
            count = len(objs)

            moving = any(o.velocity_norm and o.velocity_norm > 0.05 for o in objs)

            cls_phrase = f"{cls} approaching" if moving else cls
            plural = self._pluralize(cls)

            if count == 1:
                phrases.append(f"{cls_phrase} {direction}, {distance}")
            elif count <= 3:
                phrases.append(f"{count} {plural} {direction}, {distance}")
            else:
                phrases.append(f"several {plural} {direction}, {distance}")

        if phrases:
            await self._emit(
                self._create_intent("info", ". ".join(phrases), 2, None, 3.5)
            )
    async def _handle_threat(self, threat):
        if self.mode_state.search_mode and threat.threat_level < 3:
            return
        logger.info(
            f"[Rule] THREAT IN -> {threat.object_id} "
            f"| lvl={threat.threat_level} "
            f"| dist={threat.depth_bucket}"
        )

        now = time.time()
        last = self.object_last_announced.get(threat.object_id)
        prev_level = getattr(self, "_last_threat_level", {}).get(threat.object_id)
        escalating = prev_level is not None and threat.threat_level > prev_level

        # allow escalation bypass
        if (
                last
                and now - last < self.cooldown_sec
                and (prev_level is None or threat.threat_level <= prev_level)
        ):
            logger.info(f"[Rule] SUPPRESS cooldown -> {threat.object_id}")
            return

        # store level
        if not hasattr(self, "_last_threat_level"):
            self._last_threat_level = {}

        self._last_threat_level[threat.object_id] = threat.threat_level

        self.object_last_announced[threat.object_id] = now

        direction = (
            "on your left" if threat.horizontal_offset_norm < -0.25
            else "on your right" if threat.horizontal_offset_norm > 0.25
            else "ahead"
        )

        is_moving = threat.reason in ["approaching", "intercepting"]

        DANGEROUS_CLASSES = {"car", "bus", "truck", "motorcycle", "bicycle"}

        is_dangerous = threat.class_name.lower() in DANGEROUS_CLASSES

        prefix = "Warning, " if (threat.threat_level == 3 and is_dangerous) else ""

        if threat.threat_level == 3:
            if escalating:
                text = f"{prefix}{threat.class_name} getting very close {direction}"
            else:
                text = f"{prefix}{threat.class_name} {'approaching' if is_moving else 'very close'} {direction}"
        elif threat.threat_level == 2:
            text = f"{threat.class_name} {'approaching' if is_moving else 'near'} {direction}"
        else:
            text = f"{threat.class_name} {direction}"

        await self._emit(
            self._create_intent("threat", text, 0, threat.object_id, 2.0)
        )

    async def _handle_search(self, scene):

        now = scene.timestamp
        if now - self.last_search_ts < self.search_interval:
            return

        self.last_search_ts = now

        target = self.mode_state.search_target
        if not target:
            return

        relations = self._extract_relations(scene)

        for obj in scene.objects.values():

            if obj.object_id == "USER":
                continue

            if obj.class_name.lower() != target.lower():
                continue

            rels = relations.get(obj.object_id, set())

            direction = (
                "on your left" if "left" in rels
                else "on your right" if "right" in rels
                else "ahead"
            )

            distance = (
                "very close" if "very_close" in rels
                else "near you" if "near" in rels
                else "far away"
            )

            await self._emit(
                self._create_intent(
                    "search",
                    f"{target} {distance}, {direction}",
                    1,
                    obj.object_id,
                    2.5,
                )
            )
            return

    async def _handle_command(self, payload: dict):

        text = payload.get("text", "").lower()

        if any(cmd in text for cmd in ["find", "search", "where"]):
            STOPWORDS = {"a", "the", "is", "me", "my", "to", "for", "of"}

            words = [w for w in text.split() if w not in STOPWORDS]

            if words:
                self.mode_state.search_target = words[-1]

            self.mode_state.search_mode = True
            self.mode_state.description_mode = False
            self.mode_state.navigation_mode = False

        elif "describe" in text:
            self.mode_state.description_mode = True
            self.mode_state.search_mode = False

    def _is_duplicate(self, intent):

        key = (intent.category, intent.related_object_id, intent.text)
        now = time.time()

        if self.last_spoken_key == key and now - self.last_spoken_ts < self.duplicate_window_sec:
            return True

        self.last_spoken_key = key
        self.last_spoken_ts = now
        return False

    def _create_intent(self, category, text, priority, obj_id, ttl):

        now = time.time()

        return SpeechIntent(
            intent_id=str(uuid.uuid4()),
            category=category,
            text=text,
            priority=priority,
            related_object_id=obj_id,
            created_ts=now,
            expires_ts=now + ttl,
            suppress_if_duplicate=True,
        )

    async def _emit(self, intent):

        if intent.suppress_if_duplicate and self._is_duplicate(intent):
            logger.info(f"[Rule] SUPPRESS duplicate -> {intent.text}")
            return

        # 🔥 PRINT (for terminal)
        print(
            f"[RULE-OUT] {intent.category.upper()} | "
            f"P{intent.priority} | {intent.text}"
        )

        # 🔥 LOG (for file)
        logger.info(
            f"[Rule] EMIT -> {intent.category.upper()} "
            f"| P{intent.priority} | {intent.text}"
        )
        
        await self.event_bus.publish(
            SystemEvent(
                event_id=str(uuid.uuid4()),
                event_type="SPEECH_INTENT_CREATED",
                payload=intent,
                priority=intent.priority,
                timestamp=time.time(),
            )
        )