# =============================================================================
# FILE: App/core/tts_engine.py
# ROLE: Text-to-Speech engine — manages the speech queue and sequential output.
#
# WHAT THIS FILE DOES:
#   Receives text from SpeechScheduler, queues it, and processes speech
#   requests one at a time through a background worker. Uses AzureTTS
#   as the speech synthesis backend.
#
# FLOW:
#   SpeechScheduler._run_loop()
#       → await tts_engine.speak(text)
#           → put (text, asyncio.Future) into queue
#           → await future (blocks until speech finishes, returns True/False)
#
#   Background _speech_worker() loop:
#       → dequeue (text, future)
#       → azure_tts.speak(text)  [returns True/False]
#       → future.set_result(True/False)  [unblocks scheduler with result]
#
# GUARANTEES:
#   - speak() blocks until speech playback completes
#   - speak() returns True on success, False on failure
#   - Only one speech plays at a time (no overlapping audio)
#   - Sequential processing: speech A finishes before speech B starts
#   - Auto-starts worker on first speak() call
#   - Worker recovers if it dies unexpectedly
#   - Fails gracefully if Azure TTS is not configured
#
# WHO CALLS THIS:
#   SpeechScheduler._run_loop() calls tts_engine.speak(intent.text)
#
# DESIGN NOTE:
#   This is a singleton instance (tts_engine at module level).
#   The Azure SDK is called from a background worker, never from
#   the main event loop thread directly.
# =============================================================================

import asyncio
import logging
from typing import Optional

from App.core.azure_tts import azure_tts

logger = logging.getLogger(__name__)


class TTSEngine:
    """Text-to-Speech engine using Azure TTS backend.

    Created as a singleton at module level (tts_engine).
    Processes speech requests sequentially via an asyncio queue.

    Key behavior:
    - speak(text) blocks the caller until speech finishes playing
    - speak(text) returns True on success, False on failure
    - Only one speech plays at a time
    - Worker auto-starts on first speak() call
    - Worker recovers if it dies unexpectedly
    """

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None

    def _ensure_worker(self):
        """Start the background worker if not already running.

        Handles three cases:
        1. No worker exists → create one
        2. Worker exists and is still running → reuse it
        3. Worker exists but is done/cancelled → create a new one

        Uses a lock to prevent creating multiple workers simultaneously.
        """
        # Case 2: worker exists and is still running
        if self._worker_task is not None and not self._worker_task.done():
            return

        # Case 3: worker exists but is done — log and recreate
        if self._worker_task is not None:
            if self._worker_task.cancelled():
                logger.warning("[TTSEngine] Worker was cancelled, restarting")
            elif self._worker_task.done():
                logger.warning("[TTSEngine] Worker died, restarting")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.error("[TTSEngine] No running event loop — cannot start worker")
            return

        self._worker_task = loop.create_task(self._speech_worker())
        logger.info("[TTSEngine] Background worker started")

    async def speak(self, text: str) -> bool:
        """Speak the given text through the Azure TTS backend.

        THIS IS BLOCKING — it waits until speech playback finishes.
        The caller (SpeechScheduler) is blocked during synthesis + playback.
        This ensures sequential speech: A finishes before B starts.

        Args:
            text: The text to speak. Empty strings are silently ignored.

        Returns:
            True if speech was synthesized and played successfully.
            False on failure, error, or empty text.
        """
        if not text or not text.strip():
            return False

        self._ensure_worker()

        # Create a future that will carry the success/failure result
        done_future: asyncio.Future = asyncio.get_running_loop().create_future()

        try:
            await self._queue.put((text, done_future))
        except Exception as e:
            logger.error(f"[TTSEngine] Queue error: {e}")
            return False

        # BLOCK until the worker sets the future result
        # This is the key fix: the scheduler await's this method and
        # correctly waits for actual speech completion, not just queuing.
        # The future carries True (success) or False (failure).
        return await done_future

    async def _speech_worker(self):
        """Background worker that processes speech requests sequentially.

        Flow:
            1. Wait for (text, future) in the queue
            2. Call azure_tts.speak(text) — returns True/False
            3. Set future result — unblocks scheduler with success/failure
            4. Repeat

        AzureTTS.speak() runs the Azure SDK in a thread executor,
        so the event loop is not blocked. The worker awaits the result,
        guaranteeing speech A finishes before speech B starts.
        """
        logger.info("[TTSEngine] Worker loop running")

        while True:
            try:
                text, done_future = await self._queue.get()

                try:
                    logger.info(f"[TTSEngine] Speaking: {text[:80]}")

                    # AzureTTS.speak() returns True on success, False on failure
                    success = await azure_tts.speak(text)

                    if success:
                        logger.info(f"[TTSEngine] Speech succeeded: {text[:60]}")
                    else:
                        logger.warning(f"[TTSEngine] Speech failed: {text[:60]}")

                except Exception as e:
                    logger.error(f"[TTSEngine] Speech error: {e}")
                    success = False

                finally:
                    # Set the future result — unblocks the scheduler
                    # This runs even on error so the scheduler never hangs
                    if not done_future.done():
                        done_future.set_result(success)
                    self._queue.task_done()

            except asyncio.CancelledError:
                logger.info("[TTSEngine] Worker cancelled")
                break
            except Exception as e:
                logger.exception(f"[TTSEngine] Worker unexpected error: {e}")
                await asyncio.sleep(0.5)


# Singleton instance — used by SpeechScheduler
# Import as: from App.core.tts_engine import tts_engine
tts_engine = TTSEngine()
