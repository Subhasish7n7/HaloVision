# core/speech_scheduler.py

import asyncio
import time
import uuid
import heapq
import logging
from typing import Dict, Tuple, List, Optional

from App.core.contracts import (
    SystemEvent,
    SpeechIntent,
)

from App.core.tts_engine import tts_engine

logger = logging.getLogger(__name__)


class SpeechScheduler:

    def __init__(
        self,
        event_bus,
        cooldown_sec: float = 0.6,
        dedup_window_sec: float = 2.0,
        queue_max_size: int = 50,
    ):
        self.event_bus = event_bus

        self._queue: List[Tuple[int, float, SpeechIntent]] = []
        self._current_intent: Optional[SpeechIntent] = None

        self._last_spoken: Dict[Tuple, float] = {}
        self._dedup_window_sec = dedup_window_sec

        self._cooldown_sec = cooldown_sec
        self._last_emit_ts = 0.0

        self._queue_max_size = queue_max_size

        self._lock = asyncio.Lock()
        self._runner_task: Optional[asyncio.Task] = None

    # ============================================================

    async def start(self):
        await self.event_bus.subscribe(
            "SPEECH_INTENT_CREATED",
            self._handle_intent_event,
        )

        self._runner_task = asyncio.create_task(self._run_loop())
        logger.info("[SpeechScheduler] Started")

    # ============================================================

    async def _handle_intent_event(self, event: SystemEvent):
        intent: SpeechIntent = event.payload

        async with self._lock:

            if intent.expires_ts < time.time():
                return

            if intent.suppress_if_duplicate and self._is_duplicate(intent):
                return

            logger.info(
                f"[SpeechScheduler][QUEUE] "
                f"P{intent.priority} | text='{intent.text}'"
            )

            heapq.heappush(
                self._queue,
                (intent.priority, intent.created_ts, intent)
            )

            if len(self._queue) > self._queue_max_size:
                heapq.heappop(self._queue)

    # ============================================================

    async def _run_loop(self):
        while True:
            await asyncio.sleep(0.01)

            async with self._lock:
                now = time.time()

                if now - self._last_emit_ts < self._cooldown_sec:
                    continue

                self._cleanup_expired(now)

                if not self._queue:
                    continue

                _, _, intent = heapq.heappop(self._queue)

                self._current_intent = intent

            logger.info(
                f"[SpeechScheduler][SPEAK] "
                f"P{intent.priority} | text='{intent.text}'"
            )

            # 🔥 SPEAK HERE (IMPORTANT)
            await tts_engine.speak(intent.text)

            async with self._lock:
                self._last_emit_ts = time.time()
                self._current_intent = None

    # ============================================================

    def _is_duplicate(self, intent: SpeechIntent) -> bool:
        key = (intent.category, intent.text, intent.related_object_id)
        now = time.time()

        last_ts = self._last_spoken.get(key)

        if last_ts and now - last_ts < self._dedup_window_sec:
            return True

        self._last_spoken[key] = now
        return False

    def _cleanup_expired(self, now: float):
        self._queue = [
            (p, ts, i)
            for (p, ts, i) in self._queue
            if i.expires_ts > now
        ]
        heapq.heapify(self._queue)