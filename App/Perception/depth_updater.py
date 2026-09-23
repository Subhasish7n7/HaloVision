# =============================================================================
# FILE: App/Perception/depth_updater.py
# ROLE: Async depth inference runner — decouples depth from detection.
#
# WHAT THIS FILE DOES:
#   Runs depth inference on its OWN asyncio task, separate from the
#   detection loop. This means:
#   - Detection never blocks on depth (YOLO runs at full frame rate)
#   - Depth updates at a configurable cadence (default: every 600ms)
#   - The perception system just reads the freshest depth map available
#
# WHY THIS EXISTS:
#   MiDaS depth inference is slow (~200-500ms per frame).
#   YOLO detection is fast (~30-50ms per frame).
#   If depth ran synchronously, detection would be bottlenecked by depth.
#   By running depth on a separate task, detection runs at full speed.
#
# FLOW:
#   DepthUpdater._run() loop:
#       await sleep(refresh_sec)  ← configurable, default 0.6s
#           ↓
#       read latest frame (fed by PerceptionSystem.feed())
#           ↓
#       run depth inference in a worker thread (asyncio.to_thread)
#           ↓
#       store result in self._depth (shared state)
#           ↓
#   PerceptionSystem.process_frame() reads self._depth via current()
#
# WHO CALLS THIS:
#   - main.py: creates DepthUpdater and calls start() at startup
#   - PerceptionSystem.process_frame(): calls feed() and current()
# =============================================================================

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class DepthUpdater:
    """Runs depth inference asynchronously on its own asyncio task.

    Created by main.py at startup and passed to PerceptionSystem.

    Public API:
        feed(frame):    Hand the updater the latest camera frame (latest wins)
        current():      Get the freshest depth map (returns (depth, timestamp) tuple)
        last_ms():      Get the last inference time in milliseconds
        is_ready():     Check if at least one depth map has been computed
        start():        Start the background inference loop
    """

    def __init__(self, estimator, refresh_sec: float = 0.6):
        self._estimator = estimator       # Depth estimator (MiDaS or ONNX)
        self._refresh_sec = max(0.15, refresh_sec)  # Min 150ms between depth runs
        self._frame = None                # Latest camera frame (set by feed())
        self._depth = None                # Latest depth map (set by _run())
        self._depth_ts = None             # Timestamp of latest depth map
        self._last_ms = 0.0              # Last inference time in ms
        self._worker_task = None          # The background asyncio task
        self._runs = 0                    # Number of depth runs completed

    # ----------------------------------------------------------------
    # PUBLIC API (thread-safe via GIL atomic assignment)
    # ----------------------------------------------------------------
    def feed(self, frame):
        """Hand the updater the most recent camera frame.
        Only the latest frame is kept — older frames are discarded.
        This is called by PerceptionSystem.process_frame() before reading depth."""
        self._frame = frame

    def current(self):
        """Get the freshest depth map and its timestamp.
        Returns: (depth_map, timestamp) or (None, None) if no depth computed yet.

        This is called by PerceptionSystem.process_frame() after feeding a frame.
        The depth map may be from a PREVIOUS frame (since depth runs asynchronously).
        """
        return self._depth, self._depth_ts

    def last_ms(self) -> float:
        """Return the last depth inference time in milliseconds."""
        return self._last_ms

    def is_ready(self) -> bool:
        """Check if at least one depth map has been computed."""
        return self._depth is not None

    # ----------------------------------------------------------------
    # ASYNC LOOP (runs as a background task)
    # ----------------------------------------------------------------
    async def start(self):
        """Start the background depth inference loop.
        Called once at startup from main.py."""
        self._worker_task = asyncio.create_task(self._run())
        logger.info(f"[DepthUpdater] running (refresh={self._refresh_sec:.2f}s)")

    async def _run(self):
        """Main inference loop — runs continuously in the background.

        Flow:
            1. Wait for the first frame to arrive
            2. Compute depth immediately on the first frame (for quick startup)
            3. Then wait refresh_sec between subsequent depth runs
            4. Run depth inference in a worker thread (non-blocking)
            5. Store the result in self._depth (shared state)

        The depth map stored here is read by PerceptionSystem.process_frame()
        which may be running concurrently on a different async task.
        Python's GIL makes the reference assignment atomic, so this is safe.
        """
        while True:
            frame = self._frame
            if frame is None:
                await asyncio.sleep(0.1)
                continue

            # On the very first frame, compute depth immediately (no delay)
            # so the system has depth data within ~1 cadence of startup
            delay = 0.0 if not self.is_ready() and self._runs == 0 else self._refresh_sec
            await asyncio.sleep(delay)

            t0 = time.perf_counter()
            try:
                # Run depth inference in a thread pool to avoid blocking the event loop
                # This is important because depth inference is CPU/GPU-bound
                self._depth = await asyncio.to_thread(self._estimator.predict, frame)
                self._depth_ts = time.time()
                self._runs += 1
            except Exception as e:
                logger.error(f"[DepthUpdater] predict failed: {e}")
            self._last_ms = (time.perf_counter() - t0) * 1000
