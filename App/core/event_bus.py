# core/event_bus.py
import asyncio
import logging
import time


from collections import defaultdict
from typing import Awaitable, Callable, Dict, List
from App.core.contracts import SystemEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[SystemEvent], Awaitable[None]]


class AsyncEventBus:
    """
    In-memory asynchronous publish/subscribe event bus.
    Supports debug visibility and optional awaited publishing.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._lock = asyncio.Lock()

    # ----------------------------------
    # SUBSCRIBE
    # ----------------------------------

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
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
        """
        Publish event.
        If await_handlers=True, waits for all handlers (useful for testing).
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

        tasks = []

        for handler in handlers:
            if await_handlers:
                await self._safe_execute(handler, event)
            else:
                task = asyncio.create_task(
                    self._safe_execute(handler, event)
                )
                tasks.append(task)

        if not await_handlers:
            logger.debug(
                f"[EventBus] {len(tasks)} async tasks scheduled"
            )

    # ----------------------------------
    # SAFE EXECUTION
    # ----------------------------------

    async def _safe_execute(
        self,
        handler: EventHandler,
        event: SystemEvent,
    ) -> None:
        start = time.perf_counter()

        try:
            await handler(event)

            elapsed = (time.perf_counter() - start) * 1000
            logger.debug(
                f"[EventBus] Handler {handler.__name__} "
                f"finished in {elapsed:.2f} ms"
            )

        except Exception:
            logger.exception(
                f"[EventBus] Error in handler "
                f"{handler.__name__} "
                f"for event '{event.event_type}'"
            )