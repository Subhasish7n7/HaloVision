import asyncio
import json
import numpy as np
import cv2
from fastapi import WebSocket

clients = []
SEARCH_TARGET = None


# =========================
# CLIENT MANAGEMENT
# =========================
def remove_client(ws):
    if ws in clients:
        clients.remove(ws)


async def register_client(ws: WebSocket):
    await ws.accept()
    clients.append(ws)


# =========================
# FRAME DECODER
# =========================
def decode_frame(buffer: bytes):
    np_arr = np.frombuffer(buffer, np.uint8)
    return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)


# =========================
# 🔊 SEND SPEECH TEXT
# =========================
async def send_speech_text(text: str):
    message = {"type": "speech_text", "data": text}

    for client in clients.copy():
        try:
            await client.send_json(message)
        except:
            remove_client(client)


# =========================
# RECEIVE (FRAME + MODE + SEARCH)
# =========================
async def receive_frames(ws, perception, bus):
    latest_frame = None
    lock = asyncio.Lock()

    async def receiver():
        nonlocal latest_frame
        global SEARCH_TARGET

        while True:
            try:
                msg = await ws.receive()

                # ---------- TEXT ----------
                if msg.get("text"):
                    data = json.loads(msg["text"])

                    if data.get("type") == "mode":
                        # just forward / log (no logic)
                        print("MODE:", data["data"])

                    elif data.get("type") == "search":
                        SEARCH_TARGET = data["data"].lower().strip()
                        print("SEARCH:", SEARCH_TARGET)

                # ---------- FRAME ----------
                if msg.get("bytes"):
                    async with lock:
                        latest_frame = msg["bytes"]

            except Exception:
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

                event = await asyncio.to_thread(
                    perception.process_frame, frame
                )

                await bus.publish(event)

            except Exception:
                pass

    await asyncio.gather(receiver(), processor())


# =========================
# SEND DETECTIONS
# =========================
async def send_detections(event):
    data = event.payload

    detections = [
        {
            "id": obj.object_id,
            "label": obj.class_name,
            "depth": obj.depth_norm,
            "bbox": obj.bbox,
        }
        for obj in data.active_objects.values()
    ]

    message = {"type": "detections", "data": detections}

    for client in clients.copy():
        try:
            await client.send_json(message)
        except:
            remove_client(client)