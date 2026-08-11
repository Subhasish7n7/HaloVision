"""Asynchronous depth updater.

Decouples depth inference from the detection loop: the perception pipeline
never blocks on depth. The updater runs on its own asyncio task, grabs the
latest camera frame (fed by the WebSocket processor), predicts in a worker
thread, and publishes the freshest depth map to shared state. Detection and
tracking therefore run at full rate while distance information refreshes on
an admin-configurable cadence (default 600 ms).
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class DepthUpdater:
    def __init__(self, estimator, refresh_sec: float = 0.6):
        self._estimator = estimator
        self._refresh_sec = max(0.15, refresh_sec)
        self._frame = None
        self._depth = None
        self._last_ms = 0.0
        self._worker_task = None
        self._runs = 0

    # ----------------------------------------------------------------
    # PUBLIC (thread-safe via GIL atomic assignment)
    # ----------------------------------------------------------------
    def feed(self, frame):
        """Hand the updater the most recent frame (latest wins)."""
        self._frame = frame

    def current(self):
        return self._depth

    def last_ms(self) -> float:
        return self._last_ms

    def is_ready(self) -> bool:
        return self._depth is not None

    # ----------------------------------------------------------------
    # ASYNC LOOP
    # ----------------------------------------------------------------
    async def start(self):
        self._worker_task = asyncio.create_task(self._run())
        logger.info(f"[DepthUpdater] running (refresh={self._refresh_sec:.2f}s)")

    async def _run(self):
        while True:
            frame = self._frame
            if frame is None:
                await asyncio.sleep(0.1)
                continue

            # Force one depth compute immediately on the first available
            # frame so guidance is populated within ~1 cadence of start.
            delay = 0.0 if not self.is_ready() and self._runs == 0 else self._refresh_sec
            await asyncio.sleep(delay)

            t0 = time.perf_counter()
            try:
                self._depth = await asyncio.to_thread(self._estimator.predict, frame)
                self._runs += 1
            except Exception as e:
                logger.error(f"[DepthUpdater] predict failed: {e}")
            self._last_ms = (time.perf_counter() - t0) * 1000