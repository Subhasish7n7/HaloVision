# =============================================================================
# FILE: App/core/event_bus.py
# ROLE: Async pub/sub event bus — the nervous system of HaloVision.
#
# WHAT THIS FILE DOES:
#   Provides an in-memory publish/subscribe event bus that decouples
#   all components. Any component can publish an event, and any number
#   of handlers can subscribe to receive it.
#
# WHY THIS EXISTS:
#   The event bus is the backbone of the architecture. It allows:
#   - Loose coupling: components don't know about each other
#   - Concurrency: handlers run concurrently (fire-and-forget)
#   - Extensibility: add new handlers without modifying existing code
#
# EVENT FLOW:
#   PerceptionSystem → publishes "PERCEPTION_FRAME_READY"
#       → EventBus fans out to 2 handlers:
#           1. send_detections()          → broadcasts JSON to WebSocket clients
#           2. ReasoningLayer.handle_event → evaluates threats, builds scene graph
#
#   ReasoningLayer → publishes "FRAME_ANALYSIS_READY"
#       → EventBus fans out to:
#           1. RuleEngine.handle_event → generates speech intents
#
#   RuleEngine → publishes "SPEECH_INTENT_CREATED"
#       → EventBus fans out to:
#           1. SpeechScheduler._handle_intent_event → queues for TTS
#
# WHO CREATES THIS:
#   main.py creates a single AsyncEventBus instance at module load time.
#   It's passed to ReasoningLayer, RuleEngine, and SpeechScheduler.
# =============================================================================

import asyncio
import logging
import time
from collections import defaultdict
from typing import Awaitable, Callable, Dict, List

from App.core.contracts import SystemEvent

logger = logging.getLogger(__name__)

# Type alias for event handler functions
EventHandler = Callable[[SystemEvent], Awaitable[None]]


class AsyncEventBus:
    """In-memory asynchronous publish/subscribe event bus.

    Non-blocking, concurrent execution of handlers.
    Handlers are called with asyncio.create_task() for parallel execution.

    Usage:
        bus = AsyncEventBus()
        await bus.subscribe("MY_EVENT", my_handler)
        await bus.publish(SystemEvent(event_type="MY_EVENT", ...))
    """

    def __init__(self) -> None:
        # event_type → list of handler functions
        self._subscribers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._lock = asyncio.Lock()  # Protects subscriber list modifications

    # ----------------------------------
    # SUBSCRIBE
    # ----------------------------------

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler to receive events of a given type.

        Called during startup (main.py) to wire up the pipeline.
        Multiple handlers can subscribe to the same event type.
        """
        async with self._lock:
            self._subscribers[event_type].append(handler)

        logger.info(
            f"[EventBus] Subscribed {handler.__name__} "
            f"to event '{event_type}'"
        )

    # ----------------------------------
    # PUBLISH
    # ----------------------------------

    async def publish(
        self,
        event: SystemEvent,
        await_handlers: bool = False,
    ) -> None:
        """Publish an event to all subscribed handlers.

        Input: SystemEvent with event_type set to one of:
            - "PERCEPTION_FRAME_READY" — from PerceptionSystem
            - "FRAME_ANALYSIS_READY"   — from ReasoningLayer
            - "SPEECH_INTENT_CREATED"  — from RuleEngine

        Two execution modes:
            await_handlers=True  → sequential (debug/testing only)
            await_handlers=False → concurrent (production — each handler runs in its own task)

        In concurrent mode, handlers are fire-and-forget. If one handler
        fails, others still run. Errors are logged but don't crash the system.
        """

        handlers = self._subscribers.get(event.event_type, [])

        if not handlers:
            logger.warning(
                f"[EventBus] No subscribers for '{event.event_type}'"
            )
            return

        logger.info(
            f"[EventBus] Publishing '{event.event_type}' "
            f"to {len(handlers)} handlers "
            f"(priority={event.priority})"
        )

        if await_handlers:
            # Sequential execution — for debugging/testing
            for handler in handlers:
                await self._safe_execute(handler, event)
        else:
            # Concurrent execution — each handler runs in its own asyncio task
            # This is the production path: handlers run in parallel
            for handler in handlers:
                asyncio.create_task(self._safe_execute(handler, event))

    # ----------------------------------
    # SAFE EXECUTION
    # ----------------------------------

    async def _safe_execute(
        self,
        handler: EventHandler,
        event: SystemEvent,
    ) -> None:
        """Execute a handler with error handling and performance logging.
        If the handler raises an exception, it's logged but doesn't
        affect other handlers or the caller."""
        start = time.perf_counter()

        try:
            await handler(event)

            elapsed = (time.perf_counter() - start) * 1000
            logger.debug(
                f"[EventBus] Handler {handler.__name__} "
                f"finished in {elapsed:.2f} ms"
            )

        except Exception:
            # Log the error but don't crash — other handlers must still run
            logger.exception(
                f"[EventBus] Error in handler "
                f"{handler.__name__} "
                f"for event '{event.event_type}'"
            )
