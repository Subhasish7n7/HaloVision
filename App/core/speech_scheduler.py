import asyncio
import time
import uuid
import heapq
import logging
from typing import Dict, Tuple, List, Optional

from App.core.contracts import (
    SystemEvent,
    SpeechIntent,
    SpeechAudio,   # ✅ NEW
)

from App.core.tts_engine import TTSEngine  # ✅ NEW

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

        self._queue: List[Tuple[int, float, SpeechIntent, bool]] = []
        self._current_intent: Optional[SpeechIntent] = None

        self._last_spoken: Dict[Tuple, float] = {}
        self._dedup_window_sec = dedup_window_sec

        self._cooldown_sec = cooldown_sec
        self._last_emit_ts = 0.0

        self._queue_max_size = queue_max_size

        self._lock = asyncio.Lock()
        self._runner_task: Optional[asyncio.Task] = None
        self._is_speaking: bool = False

        # ✅ INIT TTS
        self.tts = TTSEngine()

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

            interrupt = (
                    self._is_speaking and
                    self._current_intent is not None and
                    intent.priority < self._current_intent.priority
            )


            if interrupt:
                logger.info(
                    f"[INTERRUPT SIGNAL] New P{intent.priority} will interrupt "
                    f"P{self._current_intent.priority}"
                )

            should_interrupt_current = (
                    self._is_speaking and
                    self._current_intent is not None and
                    intent.priority < self._current_intent.priority
            )
            logger.info(
                f"[SpeechScheduler][QUEUE_PUSH] "
                f"P{intent.priority} | interrupt={should_interrupt_current} | "
                f"text='{intent.text}' | queue_size={len(self._queue) + 1}"
            )

            heapq.heappush(
                self._queue,
                (intent.priority, intent.created_ts, intent, should_interrupt_current)
            )

            if len(self._queue) > self._queue_max_size:
                heapq.heappop(self._queue)



    # ============================================================

    async def _run_loop(self):
        while True:
            await asyncio.sleep(0.05)

            async with self._lock:
                now = time.time()

                if now - self._last_emit_ts < self._cooldown_sec:
                    continue

                self._cleanup_expired(now)

                if not self._queue:
                    continue

                if self._current_intent is not None:
                    continue

                _, _, intent, interrupt_flag = heapq.heappop(self._queue)
                self._current_intent = intent
                self._current_interrupt_flag = interrupt_flag
                self._is_speaking = True

            logger.info(
                f"[SpeechScheduler][DEQUEUE] "
                f"P{intent.priority} | interrupt={interrupt_flag} | text='{intent.text}'"
            )
            # 🔥 DO TTS OUTSIDE LOCK
            await self._emit(intent)

            async with self._lock:
                self._last_emit_ts = time.time()
                self._current_intent = None
                self._is_speaking = False

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
            (p, ts, i, interrupt)
            for (p, ts, i, interrupt) in self._queue
            if i.expires_ts > now
        ]
        heapq.heapify(self._queue)

    # ============================================================
    # 🔥 UPDATED OUTPUT
    # ============================================================

    async def _emit(self, intent: SpeechIntent):
        interrupt = getattr(self, "_current_interrupt_flag", False)
        logger.info(
            f"[SpeechScheduler][EMIT] P{intent.priority} | "
            f"interrupt_flag={interrupt} | text='{intent.text}'"
        )

        start = time.time()

        audio_base64 = await self.tts.synthesize(intent.text)


        tts_time = (time.time() - start) * 1000
        logger.info(f"[SpeechScheduler] TTS done in {tts_time:.2f} ms")

        if not audio_base64:
            logger.warning("[SpeechScheduler] No audio -> sending TEXT-ONLY packet")



        output = SpeechAudio(
            audio_base64=audio_base64,
            text=intent.text,
            category=intent.category,
            priority=intent.priority,
            timestamp=time.time(),
            interrupt_current=interrupt,  # ✅ NEW
        )

        await self.event_bus.publish(
            SystemEvent(
                event_id=str(uuid.uuid4()),
                event_type="SPEECH_AUDIO_READY",  # ✅ NEW
                payload=output,
                priority=intent.priority,
                timestamp=time.time(),
            )
        )