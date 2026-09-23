"""Unit tests for rule engine command parsing and path analyzer."""
import os
import sys
import pytest

# Set test environment
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")


class TestRuleEngineCommandParsing:
    """Test the voice command parsing logic in RuleEngine._handle_command."""

    def _make_rule_engine(self):
        from App.core.rule_engine import RuleEngine
        from App.core.event_bus import AsyncEventBus
        bus = AsyncEventBus()
        return RuleEngine(bus)

    def test_find_command_sets_search_mode(self):
        engine = self._make_rule_engine()
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            engine._handle_command({"text": "find chair"})
        )
        assert engine.mode_state.search_mode is True
        assert engine.mode_state.search_target == "chair"

    def test_search_command_sets_search_mode(self):
        engine = self._make_rule_engine()
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            engine._handle_command({"text": "search for bottle"})
        )
        assert engine.mode_state.search_mode is True
        assert engine.mode_state.search_target == "bottle"

    def test_where_is_command(self):
        engine = self._make_rule_engine()
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            engine._handle_command({"text": "where is the door"})
        )
        assert engine.mode_state.search_mode is True
        assert "door" in engine.mode_state.search_target

    def test_describe_command(self):
        engine = self._make_rule_engine()
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            engine._handle_command({"text": "describe scene"})
        )
        assert engine.mode_state.description_mode is True

    def test_empty_command(self):
        engine = self._make_rule_engine()
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            engine._handle_command({"text": ""})
        )
        assert engine.mode_state.search_mode is False
        assert engine.mode_state.description_mode is False

    def test_unrecognized_command(self):
        engine = self._make_rule_engine()
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            engine._handle_command({"text": "hello world"})
        )
        assert engine.mode_state.search_mode is False


class TestPathAnalyzer:
    """Test path clearness analysis."""

    def _make_analyzer(self):
        from App.core.path_analyzer import PathAnalyzer
        return PathAnalyzer()

    def _make_tracking_state(self, objects):
        class TrackingState:
            def __init__(self, objs):
                self.active_objects = objs
                self.frame_width = 640
                self.frame_height = 480
        return TrackingState(objects)

    def test_empty_path_is_clear(self):
        analyzer = self._make_analyzer()
        ts = self._make_tracking_state({})
        result = analyzer.analyze(ts)
        assert result["status"] == "CLEAR"

    def test_object_far_away_is_clear(self):
        from App.core.contracts import ObjectData
        analyzer = self._make_analyzer()
        obj = ObjectData(
            object_id="track_1",
            class_name="person",
            confidence=0.9,
            bbox=(10, 10, 30, 30),
            centroid=(20, 20),
            depth_norm=0.1,  # Far away
            depth_confidence=0.8,
            horizontal_offset_norm=0.0,
            velocity_norm=None,
            direction_vector=None,
            is_stationary=True,
            is_moving_towards_user=False,
            first_seen_ts=0.0,
            last_seen_ts=0.0,
            frame_timestamp=0.0,
            track_id=1,
        )
        ts = self._make_tracking_state({"track_1": obj})
        result = analyzer.analyze(ts)
        assert result["status"] in ("CLEAR", "UNCERTAIN")

    def test_object_blocking_path(self):
        from App.core.contracts import ObjectData
        analyzer = self._make_analyzer()
        # Large object in center of frame, close
        obj = ObjectData(
            object_id="track_1",
            class_name="person",
            confidence=0.9,
            bbox=(200, 150, 440, 400),  # Center of 640x480 frame
            centroid=(320, 275),
            depth_norm=0.7,  # Close
            depth_confidence=0.9,
            horizontal_offset_norm=0.0,  # Center
            velocity_norm=None,
            direction_vector=None,
            is_stationary=True,
            is_moving_towards_user=False,
            first_seen_ts=0.0,
            last_seen_ts=0.0,
            frame_timestamp=0.0,
            track_id=1,
        )
        ts = self._make_tracking_state({"track_1": obj})
        result = analyzer.analyze(ts)
        assert result["status"] == "BLOCKED"


class TestSafetyConstants:
    """Test that safety constants are properly defined."""

    def test_depth_thresholds(self):
        from App.core.safety import DEPTH_VERY_CLOSE, DEPTH_NEAR
        assert DEPTH_VERY_CLOSE > DEPTH_NEAR

    def test_dangerous_classes(self):
        from App.core.safety import DANGEROUS_CLASSES
        assert "car" in DANGEROUS_CLASSES
        assert "truck" in DANGEROUS_CLASSES
        assert "person" not in DANGEROUS_CLASSES


class TestEventBus:
    """Test basic EventBus pub/sub."""

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self):
        from App.core.event_bus import AsyncEventBus
        from App.core.contracts import SystemEvent
        import uuid
        import time

        bus = AsyncEventBus()
        received = []

        async def handler(event):
            received.append(event)

        await bus.subscribe("TEST_EVENT", handler)

        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type="TEST_EVENT",
            payload={"data": "test"},
            priority=0,
            timestamp=time.time(),
        )
        await bus.publish(event, await_handlers=True)
        assert len(received) == 1
        assert received[0].payload["data"] == "test"

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_crash_bus(self):
        from App.core.event_bus import AsyncEventBus
        from App.core.contracts import SystemEvent
        import uuid
        import time

        bus = AsyncEventBus()
        received = []

        async def bad_handler(event):
            raise ValueError("test error")

        async def good_handler(event):
            received.append(event)

        await bus.subscribe("TEST_EVENT", bad_handler)
        await bus.subscribe("TEST_EVENT", good_handler)

        event = SystemEvent(
            event_id=str(uuid.uuid4()),
            event_type="TEST_EVENT",
            payload={"data": "test"},
            priority=0,
            timestamp=time.time(),
        )
        await bus.publish(event, await_handlers=True)
        # Good handler should still be called
        assert len(received) == 1


class TestSpeechScheduler:
    """Test speech deduplication logic."""

    def test_dedup_same_intent(self):
        from App.core.speech_scheduler import SpeechScheduler
        from App.core.event_bus import AsyncEventBus
        from App.core.contracts import SpeechIntent
        import time
        bus = AsyncEventBus()
        scheduler = SpeechScheduler(bus, cooldown_sec=0.1)

        now = time.time()
        intent1 = SpeechIntent(
            intent_id="1",
            category="threat",
            text="car on your left",
            priority=2,
            related_object_id="track_1",
            created_ts=now,
            expires_ts=now + 10,
        )
        intent2 = SpeechIntent(
            intent_id="2",
            category="threat",
            text="car on your left",
            priority=2,
            related_object_id="track_1",
            created_ts=now,
            expires_ts=now + 10,
        )

        # Record first as spoken
        scheduler._record_spoken(intent1)

        # Second should be detected as duplicate
        assert scheduler._is_duplicate(intent2) is True

    def test_dedup_different_text(self):
        from App.core.speech_scheduler import SpeechScheduler
        from App.core.event_bus import AsyncEventBus
        from App.core.contracts import SpeechIntent
        import time
        bus = AsyncEventBus()
        scheduler = SpeechScheduler(bus, cooldown_sec=0.1)

        now = time.time()
        intent1 = SpeechIntent(
            intent_id="1",
            category="threat",
            text="car on your left",
            priority=2,
            related_object_id="track_1",
            created_ts=now,
            expires_ts=now + 10,
        )
        intent2 = SpeechIntent(
            intent_id="2",
            category="threat",
            text="car on your right",
            priority=2,
            related_object_id="track_1",
            created_ts=now,
            expires_ts=now + 10,
        )

        scheduler._record_spoken(intent1)
        assert scheduler._is_duplicate(intent2) is False
