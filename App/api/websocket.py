from fastapi import WebSocket, WebSocketDisconnect
import numpy as np
import cv2
import json
import base64

from App.core.contracts import SystemEvent

connected_client: WebSocket | None = None


# =========================
# REGISTER CLIENT
# =========================
async def register_client(ws: WebSocket):
    global connected_client
    await ws.accept()
    connected_client = ws
    print("✅ Frontend connected")


# =========================
# HANDLE DISCONNECT
# =========================
def disconnect_client():
    global connected_client
    connected_client = None
    print("🔌 Frontend disconnected")


# =========================
# SEND DETECTIONS (FAST PATH)
# =========================
async def send_detections(event: SystemEvent):
    global connected_client

    if connected_client is None:
        return

    state = event.payload
    objects = state.active_objects

    detections = []

    for obj in objects.values():
        x1, y1, x2, y2 = obj.bbox

        detections.append({
            "id": obj.object_id,
            "label": obj.class_name,
            "depth": obj.obj.depth_norm,
            "bbox": [x1, y1, x2, y2]
        })

    message = {
        "type": "detections",
        "data": detections
    }

    try:
        await connected_client.send_text(json.dumps(message))
    except:
        disconnect_client()


# =========================
# SEND AUDIO (SMART PATH)
# =========================
async def send_audio(event: SystemEvent):
    global connected_client

    if connected_client is None:
        return

    audio = event.payload

    message = {
        "type": "audio",
        "audio": audio.audio_base64,
        "text": audio.text,
        "priority": audio.priority,
        "interrupt": audio.interrupt_current
    }

    try:
        await connected_client.send_text(json.dumps(message))
    except:
        disconnect_client()


# =========================
# RECEIVE FRAMES
# =========================
async def receive_frames(ws: WebSocket, perception, tracker, bus):
    try:
        while True:
            data = await ws.receive_bytes()

            np_arr = np.frombuffer(data, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if frame is None:
                continue

            tracker.set_frame(frame)

            event = perception.process_frame(frame)

            await bus.publish(event, await_handlers=False)

    except WebSocketDisconnect:
        disconnect_client()