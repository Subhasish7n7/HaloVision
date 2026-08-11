import asyncio
import json
import traceback
import time
import logging
import numpy as np
import cv2
from fastapi import WebSocket

logger = logging.getLogger(__name__)

_HIGH_THREAT = ("person", "human")
_MEDIUM_THREAT = ("car", "vehicle", "truck", "bus", "motorcycle", "bicycle", "train", "boat")


def _threat_level(label: str) -> int:
    lower = (label or "").lower()
    if any(k in lower for k in _HIGH_THREAT):
        return 3
    if any(k in lower for k in _MEDIUM_THREAT):
        return 2
    return 1

clients = []
SEARCH_TARGET = None
SEND_LOCK = asyncio.Lock()


def remove_client(ws):
    if ws in clients:
        clients.remove(ws)
        logger.info(f"Client disconnected - count: {len(clients)}")


async def register_client(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    logger.info(f"Client connected - count: {len(clients)}")


def decode_frame(buffer: bytes):
    np_arr = np.frombuffer(buffer, np.uint8)
    return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)


async def broadcast_json(message: dict):
    """Send a JSON message to every connected client, dropping dead sockets."""
    for client in clients.copy():
        try:
            async with SEND_LOCK:
                await client.send_json(message)
        except Exception as e:
            logger.error(f"Broadcast error: {e}")
            remove_client(client)


async def send_speech_text(text: str):
    await broadcast_json({"type": "speech_text", "data": text})


async def receive_frames(ws, perception, bus):
    latest_frame = None
    lock = asyncio.Lock()

    async def receiver():
        nonlocal latest_frame
        global SEARCH_TARGET

        while True:
            try:
                msg = await ws.receive()

                if msg.get("text"):
                    data = json.loads(msg["text"])

                    if data.get("type") == "mode":
                        logger.info(f"Mode change: {data['data']}")
                    elif data.get("type") == "search":
                        SEARCH_TARGET = data["data"].lower().strip()
                        logger.info(f"Search: {SEARCH_TARGET}")

                if msg.get("bytes"):
                    async with lock:
                        latest_frame = msg["bytes"]

            except Exception as e:
                logger.error(f"Receiver error: {e}")
                remove_client(ws)
                break

    async def processor():
        nonlocal latest_frame

        while True:
            await asyncio.sleep(0.005)

            frame_data = None

            async with lock:
                if latest_frame:
                    frame_data = latest_frame
                    latest_frame = None

            if not frame_data:
                continue

            try:
                frame = decode_frame(frame_data)
                if frame is None:
                    continue

                start = time.time()
                event = await asyncio.to_thread(perception.process_frame, frame)
                proc_time = time.time() - start
                logger.debug(f"Frame processed in {proc_time:.3f}s")

                await bus.publish(event)

            except Exception as e:
                logger.error(f"Processor error: {e}")

    await asyncio.gather(receiver(), processor())


async def send_detections(event):
    data = event.payload

    detections = [
        {
            "id": obj.object_id,
            "track_id": obj.track_id,
            "label": obj.class_name,
            "confidence": obj.confidence,
            "depth": obj.depth_norm,
            "bbox": obj.bbox,
            "threat_level": _threat_level(obj.class_name),
        }
        for obj in data.active_objects.values()
    ]

    message = {"type": "detections", "data": detections}
    if getattr(data, "perf", None):
        message["perf"] = data.perf

    await broadcast_json(message)
