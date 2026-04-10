import time
import uuid
import logging

from App.core.contracts import TrackingState, SystemEvent

logger = logging.getLogger(__name__)


async def publish(bus, objs, fid):
    logging.info(f"[Reasoning] FRAME {fid}")

    now = time.time()
    for o in objs.values():
        o.frame_timestamp = now

    event = SystemEvent(
        event_id=str(uuid.uuid4()),
        event_type="PERCEPTION_FRAME_READY",
        payload=TrackingState(objs, fid, now),
        priority=1,
        timestamp=now,
    )

    await bus.publish(event, await_handlers=True)