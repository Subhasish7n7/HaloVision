# =============================================================================
# FILE: App/core/rule_engine.py
# ROLE: Rule Engine — generates speech intents from scene analysis.
#
# WHAT THIS FILE DOES:
#   Takes the FrameAnalysis from ReasoningLayer and generates speech intents
#   (what should be spoken aloud). Handles three modes:
#   1. Navigation mode: describe nearby objects for orientation
#   2. Search mode: find a specific object type and announce its location
#   3. Threat mode: announce approaching threats
#
# FLOW:
#   EventBus delivers "FRAME_ANALYSIS_READY" event
#       ↓
#   RuleEngine.handle_event() → _handle_frame()
#       ↓
#   Check for threats → _handle_threat() → emit "SPEECH_INTENT_CREATED"
#   Check mode:
#     - search_mode → _handle_search() → emit "SPEECH_INTENT_CREATED"
#     - navigation_mode → _handle_navigation() → emit "SPEECH_INTENT_CREATED"
#       ↓
#   EventBus → SpeechScheduler → TTSEngine → audio playback
#
# SPEECH INTENT DEDUPLICATION:
#   The RuleEngine prevents repeated announcements:
#   - Per-object cooldown (3.5 seconds between announcements)
#   - Duplicate text detection (2-second window)
#   - Escalation bypass (level 3 can repeat if threat is escalating)
#
# WHO CALLS THIS:
#   EventBus calls handle_event() when "FRAME_ANALYSIS_READY" is published
#
# WHERE THE RESULT GOES:
#   Publishes "SPEECH_INTENT_CREATED" → EventBus → SpeechScheduler → TTS
# =============================================================================

# core/rule_engine.py
import asyncio
import time
import uuid
from typing import Dict
from collections import defaultdict
import logging

from App.core.contracts import (
    SystemEvent,
    FrameAnalysis,
    SpeechIntent,
    ModeState,
)
from App.core.safety import DANGEROUS_CLASSES, DEPTH_VERY_CLOSE, DEPTH_NEAR
from App.core.path_analyzer import path_analyzer

logger = logging.getLogger(__name__)


class RuleEngine:
    """Generates speech intents from scene analysis.

    Who creates this: main.py creates a single instance at startup.
    Who calls handle_event(): EventBus (when "FRAME_ANALYSIS_READY" is published).

    The RuleEngine maintains state across frames:
    - mode_state: current operating mode (navigation/search/threat/description)
    - object_last_announced: cooldown tracking per object
    - last_spoken_key: duplicate detection
    """

    def __init__(self, event_bus):
        self.event_bus = event_bus
        self.mode_state = ModeState()  # Current operating mode

        # Deduplication state
        self.last_spoken_key = None
        self.last_spoken_ts = 0.0
        self.duplicate_window_sec = 2    # Seconds between identical announcements

        # Per-object cooldown state
        self.object_last_announced: Dict[str, float] = {}
        self.cooldown_sec = 3.5          # Seconds between announcements per object

        # Rate limiting
        self.last_search_ts = 0
        self.search_interval = 0.8       # Min seconds between search announcements
        self.latest_frame_ts = 0
        self.last_nav_ts = 0.0
        self.nav_interval = 0.6          # Min seconds between navigation announcements
        self.last_no_threat_ts = 0
        self.no_threat_interval = 3.0    # Seconds between "no threats" announcements

        # Hand gesture state
        self._last_tracking_state = None  # Latest TrackingState for path analysis
        self._gesture_cooldown_sec = 4.0  # Min seconds between gesture analyses
        self._last_gesture_ts = 0.0
        self._cleanup_counter = 0  # Frame counter for periodic cleanup

    # ============================================================
    # EVENT HANDLER
    # ============================================================

    async def handle_event(self, event: SystemEvent):
        """Main event dispatcher — routes events to the appropriate handler.

        Handles four event types:
        - FRAME_ANALYSIS_READY: process the scene analysis
        - USER_COMMAND_RECEIVED: handle voice commands (search, describe)
        - MODE_CHANGED: update the operating mode
        - HAND_GESTURE_DETECTED: trigger path-clear analysis
        """

        if event.event_type == "FRAME_ANALYSIS_READY":
            frame = event.payload
            await self._handle_frame(frame)

        elif event.event_type == "USER_COMMAND_RECEIVED":
            await self._handle_command(event.payload)

        elif event.event_type == "MODE_CHANGED":
            new_state = event.payload
            for field, value in new_state.__dict__.items():
                if value is not None:
                    setattr(self.mode_state, field, value)

        elif event.event_type == "HAND_GESTURE_DETECTED":
            await self._handle_gesture(event.payload)

    # ============================================================
    # CORE FRAME HANDLER
    # ============================================================

    async def _handle_frame(self, frame: FrameAnalysis):
        """Process a FrameAnalysis and generate speech intents.

        Priority order:
        1. High threats (level 3) — always announced first
        2. Medium threats (level 2) — announced if no high threats
        3. Mode-specific handling:
           - threat_mode: announce "no threats" if none found
           - search_mode: find and announce search target
           - navigation_mode: describe nearby objects
        """
        start = time.time()
        logger.info(f"[Rule] FRAME {frame.frame_id} | threats={len(frame.threats)}")

        # Skip out-of-order frames (from async processing)
        if frame.timestamp < self.latest_frame_ts:
            return

        self.latest_frame_ts = frame.timestamp

        # Store latest frame data for gesture-triggered path analysis
        self._last_frame_analysis = frame

        # Periodic cleanup of unbounded dicts (every 100 frames)
        self._cleanup_counter += 1
        if self._cleanup_counter % 100 == 0:
            now = time.time()
            cutoff = now - 300.0  # 5 minutes
            stale = [k for k, v in self.object_last_announced.items() if v < cutoff]
            for k in stale:
                del self.object_last_announced[k]
            if hasattr(self, '_last_threat_level'):
                stale_tl = [k for k in self._last_threat_level if k not in self.object_last_announced]
                for k in stale_tl:
                    del self._last_threat_level[k]
            if stale:
                logger.info(f"[Rule] Cleaned {len(stale)} stale cooldown entries")

        scene = frame.scene_graph
        threats = frame.threats

        self._last_frame_threats = threats
        has_high_priority_threat = any(t.threat_level >= 2 for t in threats)

        HIGH = [t for t in threats if t.threat_level == 3]
        MID = [t for t in threats if t.threat_level == 2]

        # Handle highest-priority threat first
        if HIGH:
            await self._handle_threat(HIGH[0])
        elif MID:
            await self._handle_threat(MID[0])

        # In threat mode, announce when no threats are present
        if self.mode_state.threat_mode:
            now = frame.timestamp

            if not threats and now - self.last_no_threat_ts > self.no_threat_interval:
                self.last_no_threat_ts = now

                await self._emit(
                    self._create_intent("threat", "No threats nearby", 1, None, 2.0)
                )
            return

        # If there's a high-priority threat, skip navigation/search
        if has_high_priority_threat:
            return

        # Mode-specific handling
        if self.mode_state.search_mode:
            await self._handle_search(scene)
            return

        if self.mode_state.description_mode:
            await self._handle_description(scene)
            return

        await self._handle_navigation(scene)
        logger.debug(f"[PERF] rule={(time.time() - start) * 1000:.1f}ms")


    def _extract_relations(self, scene):
        """Extract spatial relations from the scene graph.
        Returns a dict: object_id → set of relation types (left, right, very_close, etc.)"""
        rel_map = defaultdict(set)
        for rel in scene.relations:
            if rel.object_id == "USER":
                rel_map[rel.subject_id].add(rel.relation_type)
        return rel_map

    def _pluralize(self, word):
        """Simple English pluralization for speech generation."""
        if word == "person":
            return "people"
        if word.endswith(("s", "x", "z", "ch", "sh")):
            return word + "es"
        return word + "s"

    async def _handle_navigation(self, scene):
        """Generate navigation speech — describes nearby objects for orientation.

        Flow:
            1. Extract spatial relations from scene graph
            2. Filter out threats (already announced) and low-confidence objects
            3. Group objects by (class, direction, distance)
            4. Generate phrases like "person on your left, nearby"
            5. Limit to 2 phrases per announcement
            6. Rate-limit to prevent speech overload
        """
        now = scene.timestamp

        if now - self.last_nav_ts < self.nav_interval:
            return

        self.last_nav_ts = now

        relations = self._extract_relations(scene)

        # Get IDs of objects that are already being announced as threats
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
                continue
            if obj.confidence < 0.5:
                continue

            is_approaching = obj.velocity_norm and obj.velocity_norm > 0

            # Skip far-away non-approaching objects
            if obj.depth_norm < 0.3 and not is_approaching:
                continue
            rels = relations.get(obj.object_id, set())

            direction = (
                "on your left" if "left" in rels
                else "on your right" if "right" in rels
                else "ahead"
            )

            if obj.depth_norm >= DEPTH_VERY_CLOSE:
                distance = "very close"
            elif obj.depth_norm >= DEPTH_NEAR:
                distance = "near you"
            else:
                distance = "far away"

            grouped[(obj.class_name, direction, distance)].append(obj)

        # Build speech phrases from grouped objects
        phrases = []

        # Sort by distance (closest first)
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

        # Limit to 2 phrases per announcement
        if len(phrases) > 2:
            phrases = phrases[:2]

        if phrases:
            now = scene.timestamp

            if not hasattr(self, "_last_nav_repeat_ts"):
                self._last_nav_repeat_ts = 0

            REPEAT_INTERVAL = 2.5
            if now - self._last_nav_repeat_ts > REPEAT_INTERVAL:
                self._last_nav_repeat_ts = now

                await self._emit(
                    self._create_intent("info", ". ".join(phrases), 2, None, 3.5)
                )

    async def _handle_description(self, scene):
        """Generate a full scene description when description_mode is active.

        Builds a comprehensive natural-language description of all detected
        objects, their positions, distances, and the overall scene type.
        """
        relations = self._extract_relations(scene)

        real_objects = [
            obj for obj in scene.objects.values()
            if obj.object_id != "USER" and obj.confidence >= 0.4
        ]

        if not real_objects:
            text = (
                "I don't see any clearly recognisable objects in this scene. "
                "The frame appears to be empty or low-light."
            )
            await self._emit(
                self._create_intent("info", text, 0, None, 8.0)
            )
            try:
                from App.api import webRTC
                await webRTC.broadcast_json({
                    "type": "speech_text",
                    "data": text,
                })
            except Exception as e:
                logger.warning(f"[SCENE] Failed to broadcast empty description via WebSocket: {e}")
            return

        by_class = {}
        for obj in real_objects:
            by_class.setdefault(obj.class_name, []).append(obj)

        parts = []
        for cls, objs in by_class.items():
            sample = max(objs, key=lambda o: o.confidence)
            rels = relations.get(sample.object_id, set())

            direction = ""
            if "left" in rels:
                direction = " on your left"
            elif "right" in rels:
                direction = " on your right"

            if sample.depth_norm >= DEPTH_VERY_CLOSE:
                distance = " very close"
            elif sample.depth_norm >= DEPTH_NEAR:
                distance = " nearby"
            else:
                distance = " further away"

            count = len(objs)
            if count > 1:
                parts.append(f"{count} {self._pluralize(cls)}{direction}{distance}")
            else:
                parts.append(f"a {cls}{direction}{distance}")

        if len(parts) == 1:
            detail = parts[0]
        elif len(parts) == 2:
            detail = f"{parts[0]} and {parts[1]}"
        else:
            detail = f"{parts[0]}, {parts[1]}, and {parts[2]}"

        total = len(real_objects)
        vehicle_like = any(
            k in by_class
            for k in ("car", "bus", "truck", "motorcycle", "train", "bicycle", "boat")
        )
        scene_type = "an outdoor environment" if vehicle_like else "an indoor environment"

        text = (
            f"I see {detail}. "
            f"There {'is' if total == 1 else 'are'} {total} object{'s' if total != 1 else ''} "
            f"in view and the scene looks like {scene_type}."
        )

        logger.info(f"[SCENE] Description generated: {text}")
        await self._emit(
            self._create_intent("info", text, 0, None, 8.0)
        )

        try:
            from App.api import webRTC
            await webRTC.broadcast_json({
                "type": "speech_text",
                "data": text,
            })
        except Exception as e:
            logger.warning(f"[SCENE] Failed to broadcast description via WebSocket: {e}")

        self.mode_state.description_mode = False

    async def _handle_threat(self, threat):
        """Generate a threat announcement speech intent.

        Includes:
        - Direction (left/right/ahead)
        - Distance (very close/nearby)
        - Movement status (approaching/intercepting)
        - "Warning" prefix for dangerous classes at level 3

        Cooldown logic:
        - Per-object cooldown (3.5 seconds)
        - Escalation bypass: if threat level increased, announce immediately
        """
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

        # Cooldown: suppress if recently announced (unless escalating)
        if (
                last
                and now - last < self.cooldown_sec
                and (prev_level is None or threat.threat_level <= prev_level)
        ):
            logger.info(f"[Rule] SUPPRESS cooldown -> {threat.object_id}")
            return

        # Store current threat level for escalation detection
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
        is_dangerous = threat.class_name.lower() in DANGEROUS_CLASSES

        # Add "Warning" prefix for dangerous vehicles at level 3
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
        """Generate search mode speech — announce when the target is found.

        Flow:
            1. Check if a search target is set
            2. Find objects matching the target class
            3. Announce direction and distance of the match
            4. Rate-limit to prevent spam
        """
        now = scene.timestamp
        if now - self.last_search_ts < self.search_interval:
            return

        self.last_search_ts = now

        target = self.mode_state.search_target
        if not target:
            await self._emit(
                self._create_intent("search", "No target specified", 1, None, 2.0)
            )
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

    # ============================================================
    # HAND GESTURE → PATH CLEARNESS ANALYSIS
    # ============================================================

    async def _handle_gesture(self, payload: dict):
        """Handle a raised-hand gesture from the frontend.

        The gesture acts as a command: "Is the path clear?"
        Uses the latest frame's detections to analyze path clearness.
        Produces a single TTS announcement with the result.

        Debounce: ignores gestures within _gesture_cooldown_sec of the last one.
        This prevents continuous triggering when the hand stays raised.
        """
        now = time.time()

        # Debounce: ignore if too soon since last gesture analysis
        if now - self._last_gesture_ts < self._gesture_cooldown_sec:
            logger.info("[Rule] GESTURE suppressed (cooldown)")
            return

        gesture = payload.get("gesture", "")
        if gesture != "open_palm":
            return

        logger.info("[Rule] HAND GESTURE DETECTED — triggering path analysis")

        # Use the latest frame analysis for path evaluation
        frame = getattr(self, "_last_frame_analysis", None)
        if frame is None:
            logger.warning("[Rule] No frame data available for path analysis")
            await self._emit(
                self._create_intent(
                    "path_check",
                    "I can't confirm the path is clear.",
                    0,
                    None,
                    3.0,
                )
            )
            return

        # Build a lightweight tracking state from the scene graph
        # The scene_graph.objects contains the same ObjectData instances
        # that were built by PerceptionSystem
        scene = frame.scene_graph

        class _TrackingStateProxy:
            """Minimal proxy so PathAnalyzer can access active_objects."""
            def __init__(self, objects, w, h):
                self.active_objects = objects
                self.frame_width = w
                self.frame_height = h

        proxy = _TrackingStateProxy(
            objects=scene.objects,
            w=getattr(frame, "frame_width", 0) or 640,
            h=getattr(frame, "frame_height", 0) or 480,
        )

        # Run path analysis (CPU-bound but fast — no ML inference)
        result = await asyncio.to_thread(path_analyzer.analyze, proxy)

        status = result["status"]
        message = result["message"]
        confidence = result["confidence"]

        logger.info(
            f"[Rule] PATH ANALYSIS → {status} | "
            f"confidence={confidence:.2f} | "
            f"obstacles={len(result.get('obstacles', []))}"
        )

        # Emit as a speech intent
        await self._emit(
            self._create_intent(
                "path_check",
                message,
                0,  # highest priority — user explicitly asked
                None,
                3.0,
            )
        )

        # Broadcast path status to frontend via WebSocket
        try:
            from App.api import webRTC
            await webRTC.broadcast_json({
                "type": "path_status",
                "data": {
                    "status": status,
                    "message": message,
                    "confidence": round(confidence, 2),
                },
            })
        except Exception as e:
            logger.warning(f"[Rule] Failed to broadcast path status: {e}")

        self._last_gesture_ts = now

    # ============================================================
    # VOICE COMMANDS
    # ============================================================

    async def _handle_command(self, payload: dict):
        """Handle voice commands from the user.
        Parses the command text and updates the operating mode.

        Supported commands:
        - "find {object}" / "search {object}" / "where is {object}" → search mode
        - "describe" → description mode
        """
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
        """Check if this intent was recently spoken (deduplication).
        Uses a key of (category, object_id, text) with a 2-second window."""
        key = (intent.category, intent.related_object_id, intent.text)
        now = time.time()

        if self.last_spoken_key == key and now - self.last_spoken_ts < self.duplicate_window_sec:
            return True

        self.last_spoken_key = key
        self.last_spoken_ts = now
        return False

    def _create_intent(self, category, text, priority, obj_id, ttl):
        """Create a SpeechIntent with a unique ID and expiry time."""
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
        """Publish a SpeechIntent to the EventBus.

        Flow:
            SpeechIntent → SystemEvent("SPEECH_INTENT_CREATED")
                → EventBus → SpeechScheduler._handle_intent_event()
                    → SpeechScheduler._run_loop() → TTSEngine.speak()
        """
        if intent.suppress_if_duplicate and self._is_duplicate(intent):
            logger.info(f"[Rule] SUPPRESS duplicate -> {intent.text}")
            return

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
