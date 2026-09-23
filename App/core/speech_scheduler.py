# =============================================================================
# FILE: App/core/speech_scheduler.py
# ROLE: Speech scheduler — queues and deduplicates speech intents before TTS.
#
# WHAT THIS FILE DOES:
#   Subscribes to "SPEECH_INTENT_CREATED" events and manages a priority queue
#   of speech intents. Processes them one at a time, feeding each to the TTS engine.
#
# FLOW:
#   EventBus delivers "SPEECH_INTENT_CREATED"
#       ↓
#   _handle_intent_event() → validate, dedup, enqueue to priority queue
#       ↓
#   _run_loop() → dequeue highest-priority intent
#       → check expiration (intent may have expired while queued)
#       → enforce cooldown (respect _cooldown_sec after last successful speech)
#       → await tts_engine.speak(text) → returns True/False
#       → if success: update _last_spoken and _last_emit_ts
#       → if failure: do NOT update (allows retry and avoids false cooldown)
#
# DEDUPLICATION:
#   - Per-object dedup window: 300 seconds (5 minutes)
#   - Same tracked object (category + text + object_id) won't be re-announced
#     for 5 minutes after successful speech
#   - Different tracked objects are deduplicated independently
#   - Expired intents (past expires_ts) are silently dropped when queued
#   - Expired intents are also checked again immediately before speaking
#   - _last_spoken is updated ONLY after successful speech, not when queued
#   - Stale _last_spoken entries are cleaned up periodically
#
# QUEUE OVERFLOW:
#   - Queue has a max size (default 50)
#   - When full, the LOWEST priority item (highest priority number) is removed
#   - Ties broken by removing the oldest item (lowest created_ts)
#
# COOLDOWN:
#   - After a successful speech, waits _cooldown_sec before starting the next
#   - Cooldown only starts after successful speech, not after failures
#   - Uses asyncio.sleep (non-blocking) to wait
#   - Re-checks expiration after cooldown wait
#
# WHO CREATES THIS:
#   main.py creates a single instance and calls start() at startup.
#   It subscribes itself to "SPEECH_INTENT_CREATED" events.
#
# WHERE THE RESULT GOES:
#   tts_engine.speak() → TTSEngine worker → AzureTTS → Azure Speech SDK → speaker
# =============================================================================

import asyncio
import time
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
    """Priority-based speech queue with deduplication.

    Who creates this: main.py creates a single instance at startup.
    Who calls _handle_intent_event(): EventBus (when "SPEECH_INTENT_CREATED" is published).

    The scheduler runs its own background loop (_run_loop) that processes
    intents from the priority queue one at a time.
    """

    def __init__(
        self,
        event_bus,
        cooldown_sec: float = 0.6,
        dedup_window_sec: float = 300.0,
        queue_max_size: int = 50,
    ):
        self.event_bus = event_bus

        # Priority queue: (priority, timestamp, SpeechIntent)
        # Lower priority number = higher importance = spoken first
        self._queue: List[Tuple[int, float, SpeechIntent]] = []
        self._current_intent: Optional[SpeechIntent] = None

        # Deduplication state
        # _last_spoken maps (category, text, object_id) → timestamp of LAST SUCCESSFUL speech
        self._last_spoken: Dict[Tuple, float] = {}
        self._dedup_window_sec = dedup_window_sec

        # Rate limiting
        # _last_emit_ts is the timestamp of the last SUCCESSFULLY completed speech
        self._cooldown_sec = cooldown_sec
        self._last_emit_ts = 0.0

        self._queue_max_size = queue_max_size

        self._lock = asyncio.Lock()
        self._runner_task: Optional[asyncio.Task] = None

    # ============================================================
    # STARTUP
    # ============================================================

    async def start(self):
        """Subscribe to speech intent events and start the processing loop.
        Called once at startup from main.py."""
        await self.event_bus.subscribe(
            "SPEECH_INTENT_CREATED",
            self._handle_intent_event,
        )

        self._runner_task = asyncio.create_task(self._run_loop())
        logger.info("[SpeechScheduler] Started")

    # ============================================================
    # EVENT HANDLER
    # ============================================================

    async def _handle_intent_event(self, event: SystemEvent):
        """Handle incoming speech intent events from the EventBus.
        Validates, deduplicates, and adds to the priority queue."""
        intent: SpeechIntent = event.payload

        async with self._lock:
            now = time.time()

            # Drop expired intents
            if intent.expires_ts < now:
                logger.debug(
                    f"[SpeechScheduler] Dropped expired intent: '{intent.text}' "
                    f"(expired {now - intent.expires_ts:.1f}s ago)"
                )
                return

            # Drop duplicate intents (pure check — no side effects)
            if intent.suppress_if_duplicate and self._is_duplicate(intent):
                logger.debug(
                    f"[SpeechScheduler] Dropped duplicate: '{intent.text}'"
                )
                return

            logger.info(
                f"[SpeechScheduler][ENQUEUE] "
                f"P{intent.priority} | text='{intent.text}' | "
                f"cat={intent.category} | obj={intent.related_object_id}"
            )

            # Add to priority queue (heap)
            heapq.heappush(
                self._queue,
                (intent.priority, intent.created_ts, intent)
            )

            # Trim queue if it exceeds max size
            # Remove the LOWEST priority item (highest priority number)
            # Ties broken by oldest (lowest created_ts)
            if len(self._queue) > self._queue_max_size:
                worst_idx = max(
                    range(len(self._queue)),
                    key=lambda i: (self._queue[i][0], -self._queue[i][1])
                )
                removed = self._queue.pop(worst_idx)
                heapq.heapify(self._queue)
                logger.info(
                    f"[SpeechScheduler] Queue overflow — dropped lowest priority: "
                    f"'{removed[2].text}' (P{removed[0]})"
                )

    # ============================================================
    # PROCESSING LOOP
    # ============================================================

    async def _run_loop(self):
        """Background loop that processes speech intents from the queue.

        Flow:
            1. Wait 100ms
            2. Clean up expired intents from queue
            3. Pop the highest-priority intent from the queue
            4. Check expiration again (intent may have expired while queued)
            5. Enforce cooldown (wait if needed after last successful speech)
            6. Re-check expiration after cooldown (intent may have expired during wait)
            7. Send text to TTSEngine for synthesis and playback
            8. If success: update _last_spoken and _last_emit_ts
            9. If failure: do NOT update (allows retry)

        This ensures only one speech plays at a time (no overlapping audio).
        tts_engine.speak() blocks until Azure TTS finishes playback.
        """
        logger.info("[SpeechScheduler] Run loop started")

        cleanup_counter = 0

        while True:
            try:
                await asyncio.sleep(0.1)

                async with self._lock:
                    # Clean up expired intents from the queue
                    self._cleanup_expired(time.time())

                    # Periodically clean up stale _last_spoken entries (every ~60s)
                    cleanup_counter += 1
                    if cleanup_counter >= 600:
                        cleanup_counter = 0
                        self._cleanup_stale_spoken(time.time())

                    if len(self._queue) == 0:
                        continue

                    # Pop the highest-priority (lowest number) intent
                    _, _, intent = heapq.heappop(self._queue)

                # ---- PRE-SPEAK EXPIRATION CHECK ----
                # Intent may have expired while waiting in the queue
                now = time.time()
                if intent.expires_ts < now:
                    logger.info(
                        f"[SpeechScheduler] Discarded expired intent: "
                        f"'{intent.text}' (expired {now - intent.expires_ts:.1f}s ago)"
                    )
                    continue

                # ---- COOLDOWN ----
                # Wait if needed after last successful speech
                if self._last_emit_ts > 0:
                    elapsed = now - self._last_emit_ts
                    if elapsed < self._cooldown_sec:
                        wait_time = self._cooldown_sec - elapsed
                        logger.debug(
                            f"[SpeechScheduler] Cooldown: waiting {wait_time:.2f}s"
                        )
                        # Release lock during cooldown wait
                        await asyncio.sleep(wait_time)

                        # Re-check expiration after cooldown
                        now = time.time()
                        if intent.expires_ts < now:
                            logger.info(
                                f"[SpeechScheduler] Discarded intent expired "
                                f"during cooldown: '{intent.text}'"
                            )
                            continue

                # ---- SPEAK ----
                logger.info(
                    f"[SpeechScheduler][SPEAK] "
                    f"P{intent.priority} | text='{intent.text}'"
                )

                # Send to TTS engine — this blocks until speech is complete
                # Returns True on success, False on failure
                success = await tts_engine.speak(intent.text)

                if success:
                    # ---- SUCCESS: update dedup + cooldown timestamps ----
                    self._record_spoken(intent)
                    self._last_emit_ts = time.time()
                    logger.info(
                        f"[SpeechScheduler][SPOKEN] '{intent.text}'"
                    )
                else:
                    # ---- FAILURE: do NOT update timestamps ----
                    # This allows the same text to be retried later
                    # and avoids penalizing cooldown for failed speech
                    logger.warning(
                        f"[SpeechScheduler][FAILED] '{intent.text}' "
                        f"— not recording as spoken"
                    )

            except asyncio.CancelledError:
                logger.info("[SpeechScheduler] Run loop cancelled")
                break
            except Exception as e:
                logger.exception(f"[SpeechScheduler] Run loop error: {e}")
                await asyncio.sleep(0.5)

    # ============================================================
    # DEDUPLICATION
    # ============================================================

    def _is_duplicate(self, intent: SpeechIntent) -> bool:
        """Check if this intent was recently SPOKEN (not just queued).

        Uses a key of (category, text, object_id) with a configurable window.
        This is a pure check — it does NOT update _last_spoken.
        _last_spoken is updated only by _record_spoken() after successful speech.
        """
        key = (intent.category, intent.text, intent.related_object_id)
        now = time.time()

        last_ts = self._last_spoken.get(key)

        if last_ts and now - last_ts < self._dedup_window_sec:
            return True

        return False

    def _record_spoken(self, intent: SpeechIntent):
        """Record that an intent was successfully spoken.

        Called ONLY after tts_engine.speak() returns True.
        Updates _last_spoken with the current timestamp.
        """
        key = (intent.category, intent.text, intent.related_object_id)
        self._last_spoken[key] = time.time()

    def _cleanup_expired(self, now: float):
        """Remove expired intents from the queue."""
        before = len(self._queue)
        self._queue = [
            (p, ts, i)
            for (p, ts, i) in self._queue
            if i.expires_ts > now
        ]
        after = len(self._queue)
        if before != after:
            logger.debug(
                f"[SpeechScheduler] Cleaned up {before - after} expired intents"
            )
            heapq.heapify(self._queue)

    def _cleanup_stale_spoken(self, now: float):
        """Remove stale entries from _last_spoken to prevent unbounded growth.

        Entries older than dedup_window_sec + 60s margin are removed.
        This runs periodically and does not affect active deduplication.
        """
        if not self._last_spoken:
            return
        cutoff = now - self._dedup_window_sec - 60.0
        stale_keys = [
            key for key, ts in self._last_spoken.items()
            if ts < cutoff
        ]
        for key in stale_keys:
            del self._last_spoken[key]
        if stale_keys:
            logger.debug(
                f"[SpeechScheduler] Cleaned up {len(stale_keys)} stale dedup entries"
            )
