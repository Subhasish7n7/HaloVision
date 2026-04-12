# core/main.py
import asyncio
import logging
import os
import time
import uuid

from App.Perception.run_perception import process_frame # added
from App.core.event_bus import AsyncEventBus
from App.core.reasoning_layer import ReasoningLayer
from App.core.rule_engine import RuleEngine
from App.core.contracts import ObjectData, TrackingState, SystemEvent


# ============================================================
# LOGGING
# ============================================================

def setup_logging(name):
    os.makedirs("log/reasoning_log", exist_ok=True)
    os.makedirs("log/rule_log", exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    for h in root.handlers[:]:
        root.removeHandler(h)

    r = logging.FileHandler(f"log/reasoning_log/{name}.txt", "w")
    r.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    r.addFilter(lambda rec: "[Reasoning]" in rec.getMessage())

    rule = logging.FileHandler(f"log/rule_log/{name}.txt", "w")
    rule.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
    rule.addFilter(lambda rec: "[Rule]" in rec.getMessage())

    root.addHandler(r)
    root.addHandler(rule)


# ============================================================
# LISTENERS
# ============================================================

async def speech_listener(event):
    i = event.payload
    logging.info(f"[Rule] DECISION -> {i.category.upper()} | P{i.priority} | {i.text}")


# ============================================================
# FRAME PUBLISHER
# ============================================================

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


# ============================================================
# SETUP
# ============================================================

async def setup():
    bus = AsyncEventBus()

    r = ReasoningLayer(bus)
    rule = RuleEngine(bus)

    # 🔥 CONNECT PERCEPTION → REASONING
    await bus.subscribe("PERCEPTION_FRAME_READY", r.handle_event)
    print("✅ Perception → Reasoning CONNECTED")

    # 🔥 CONNECT REASONING → RULE
    await bus.subscribe("FRAME_ANALYSIS_READY", rule.handle_event)
    print("✅ Reasoning → RuleEngine CONNECTED")

    await bus.subscribe("USER_COMMAND_RECEIVED", rule.handle_event)

    return bus

# ============================================================
# Perception (UNCHANGED)   (Change No.1) (added)
# ============================================================

async def Perception_main():
    setup_logging("live_run")

    bus = await setup()
    # 🔥 Start real perception (camera + models)
    await process_frame(bus)


async def test_critical_threat():
    setup_logging("critical_threat")
    bus = await setup()

    depths = [3.0, 2.2, 1.4, 0.9, 0.5]
    offsets = [0.6, 0.4, 0.2, 0.1, 0.0]

    for i in range(5):
        obj = ObjectData("bike","bicycle",0.9,(0,0,0,0),(0,0),
                         depths[i],0.9,offsets[i],2.0)
        await publish(bus, {"bike": obj}, i)


async def test_duplicate():
    setup_logging("duplicate")
    bus = await setup()

    obj1 = ObjectData("p","person",0.9,(0,0,0,0),(0,0),2.0,0.9,0.0,0.0)
    obj2 = ObjectData("p","person",0.9,(0,0,0,0),(0,0),1.2,0.9,0.0,0.0)

    logging.info("[Rule] EXPECT -> first emit")
    await publish(bus, {"p": obj1}, 1)

    logging.info("[Rule] EXPECT -> suppressed duplicate")
    await publish(bus, {"p": obj1}, 2)

    logging.info("[Rule] EXPECT -> new emit after change")
    await publish(bus, {"p": obj2}, 3)


async def test_search():
    setup_logging("search")
    bus = await setup()

    await bus.publish(SystemEvent(
        event_id="cmd",
        event_type="USER_COMMAND_RECEIVED",
        payload={"text": "search chair"},
        priority=1,
        timestamp=time.time()
    ), await_handlers=True)

    obj = ObjectData("c","chair",0.9,(0,0,0,0),(0,0),1.2,0.9,0.5,0.0)

    for i in range(3):
        await publish(bus, {"c": obj}, i)
        await asyncio.sleep(0.3)


# ============================================================
# MAIN
# ============================================================

async def main():
    await test_critical_threat()
    await asyncio.sleep(2)
    await test_duplicate()
    await asyncio.sleep(2)
    await test_search()


if __name__ == "__main__":
    asyncio.run(Perception_main())