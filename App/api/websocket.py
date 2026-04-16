# App/api/websocket.py

import asyncio
import numpy as np
import cv2
from fastapi import WebSocket

clients = []


# =========================
# REGISTER CLIENT
# =========================
async def register_client(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    print("✅ Client connected")


# =========================
# FRAME DECODER
# =========================
def decode_frame(buffer: bytes) -> np.ndarray:
    np_arr = np.frombuffer(buffer, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    return frame


# =========================
# RECEIVE FRAMES (LATEST ONLY)
# =========================
async def receive_frames(ws, perception, tracker, bus):
    latest_frame = None
    lock = asyncio.Lock()

    async def receiver():
        nonlocal latest_frame
        while True:
            try:
                data = await ws.receive_bytes()

                async with lock:
                    latest_frame = data  # 🔥 overwrite old

            except Exception as e:
                print("❌ Receiver error:", e)
                break

    async def processor():
        nonlocal latest_frame

        while True:
            await asyncio.sleep(0.001)

            frame_data = None

            async with lock:
                if latest_frame is not None:
                    frame_data = latest_frame
                    latest_frame = None

            if frame_data is None:
                continue

            try:
                frame = decode_frame(frame_data)

                if frame is None:
                    continue

                tracker.set_frame(frame)

                event = await asyncio.to_thread(perception.process_frame, frame)
                await bus.publish(event)

            except Exception as e:
                print("❌ Processor error:", e)

    await asyncio.gather(receiver(), processor())


# =========================
# SEND DETECTIONS
# =========================
async def send_detections(event):
    data = event.payload

    detections = []

    for obj in data.active_objects.values():
        detections.append({
            "id": obj.object_id,
            "label": obj.class_name,
            "depth": obj.depth_norm,
            "bbox": obj.bbox,
        })

    message = {
        "type": "detections",
        "data": detections,
    }

    # 🔥 send to all clients
    await asyncio.gather(*[
        client.send_json(message)
        for client in clients
    ])


# =========================
# SEND AUDIO
# =========================
async def send_audio(event):
    payload = event.payload

    message = {
        "event_type": "SPEECH_AUDIO_READY",
        "payload": {
            "audio_base64": payload.audio_base64
        }
    }

    await asyncio.gather(*[
        client.send_json(message)
        for client in clients
    ])