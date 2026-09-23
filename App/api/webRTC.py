# =============================================================================
# FILE: App/api/webRTC.py
# ROLE: Real-time transport — WebSocket/WebRTC frame ingress + outbound broadcast.
#
# WHAT THIS FILE DOES:
#   This is the TRANSPORT LAYER — the bridge between the browser and the
#   AI pipeline. It handles:
#   1. Receiving camera frames from the browser (JPEG over WebSocket or WebRTC RTP)
#   2. Decoding frames and sending them to the Perception Layer
#   3. Broadcasting detection results and audio back to all connected clients
#
# TWO INGRESS PATHS:
#   1. /ws — Classic JPEG-over-WebSocket (fallback for all browsers)
#   2. /rtc — WebRTC RTP media (lower latency, no JPEG encode/decode)
#
# BOTH PATHS SHARE:
#   - The same client registry (clients list)
#   - The same outbound broadcast (broadcast_json)
#   - The same perception pipeline (perception.process_frame)
#
# FLOW (JPEG WebSocket /ws):
#   Browser → binary JPEG frame → ws.receive()
#       → decode_frame() → numpy BGR array
#       → perception.process_frame(frame) → SystemEvent
#       → bus.publish(event) → EventBus fans out to handlers
#           → send_detections() → broadcast_json() → all clients
#
# FLOW (WebRTC /rtc):
#   Browser → RTP video track → track.recv() → frame.to_ndarray()
#       → perception.process_frame(frame) → SystemEvent
#       → bus.publish(event) → same as above
#
# OUTBOUND FLOW:
#   EventBus handler → broadcast_json(message) → all connected WebSocket clients
#   Message types: "detections", "audio", "speech_text"
#
# WHO CREATES THIS:
#   main.py imports register_client, receive_frames, send_detections, rtc_endpoint
#   and uses them in the WebSocket route handlers.
# =============================================================================

"""Real-time media + WebSocket transport for HaloVision.

Two ingress paths share this module:

1. WebRTC (RTP) media ingress — the browser streams its camera as a real
   WebRTC MediaStream (VP8/H264 RTP) instead of uploading JPEG frames over a
   binary WebSocket. This removes the per-frame JPEG encode/decode round-trip,
   so the vision pipeline receives raw decoded frames at much lower latency
   and higher throughput.

   Signaling is a tiny WebSocket exchange on /rtc:
       browser -> server : {"type":"offer","sdp":...} + {"type":"ice",...}
       server  -> browser: {"type":"answer","sdp":...} + {"type":"ice",...}

2. Classic JPEG-frame WebSocket ingress on /ws (fallback for browsers without
   WebRTC) plus the shared OUTBOUND channel: detections and speech audio/text
   are pushed to every connected client here, regardless of which transport
   sent the frames.
"""

import asyncio
import json
import logging
import time

import numpy as np
import cv2

from fastapi import WebSocket
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate

logger = logging.getLogger(__name__)

def _threat_level(depth_norm: float) -> int:
    """Convert a depth value to a simple threat level for the frontend.
    Used by send_detections() to include threat info in the JSON broadcast.

    MiDaS convention: higher depth_norm = CLOSER to camera.
    After _normalize01(): 1.0 = closest object, 0.0 = farthest.
    """
    if depth_norm <= 0.0:
        return 0       # SAFE — no depth data available
    elif depth_norm >= 0.6:
        return 3       # HIGH — very close
    elif depth_norm >= 0.35:
        return 2       # MEDIUM — near
    elif depth_norm >= 0.15:
        return 1       # LOW — somewhat close
    else:
        return 0       # SAFE — far away

# ---------------------------------------------------------------------------
# Shared client registry + outbound broadcast (used by both transports)
# ---------------------------------------------------------------------------
clients = []                # List of connected WebSocket clients
SEARCH_TARGET = None        # Global search target (set by frontend via WebSocket)
SEND_LOCK = asyncio.Lock()  # Prevents concurrent broadcast issues


def remove_client(ws):
    """Remove a disconnected client from the registry."""
    if ws in clients:
        clients.remove(ws)
        logger.info(f"Client disconnected - count: {len(clients)}")

async def register_client(ws: WebSocket):
    """Accept a new WebSocket connection and add to the client registry.
    Called when a browser connects to /ws or /rtc.

    Resets SEARCH_TARGET to prevent stale search state from a previous session.
    """
    await ws.accept()
    clients.append(ws)
    global SEARCH_TARGET
    SEARCH_TARGET = None
    logger.info(f"Client connected - count: {len(clients)}")


def decode_frame(buffer: bytes):
    """Decode a JPEG binary buffer into an OpenCV numpy array (BGR format).
    This is the frame that will be sent to the perception pipeline."""
    np_arr = np.frombuffer(buffer, np.uint8)
    return cv2.imdecode(np_arr, cv2.IMREAD_COLOR)


async def broadcast_json(message: dict):
    """Send a JSON message to every connected client.
    Drops dead sockets automatically.

    Used by:
    - send_detections(): broadcasts detection results
    - send_speech_text(): broadcasts search announcements
    """
    for client in clients.copy():
        try:
            await client.send_json(message)
        except Exception as e:
            logger.error(f"Broadcast error: {e}")
            remove_client(client)


async def send_speech_text(text: str):
    """Broadcast a speech text message to all clients.
    Used by PerceptionSystem for search announcements."""
    await broadcast_json({"type": "speech_text", "data": text})


# ---------------------------------------------------------------------------
# JPEG-frame WebSocket ingress (/ws)
# ---------------------------------------------------------------------------
async def receive_frames(ws, perception, bus):
    """Handle JPEG frame streaming over WebSocket.

    Runs two concurrent tasks:
    - receiver(): reads incoming messages (binary JPEG frames + JSON commands)
    - processor(): decodes frames and runs the perception pipeline

    Uses an asyncio.Event for instant wake-up — the processor does NOT poll
    on a fixed timer.  When the receiver gets a frame it signals the event,
    and the processor wakes immediately.

    The "latest-frame-wins" pattern ensures the processor always works on
    the freshest frame, dropping older frames if the pipeline is slower
    than the camera frame rate.
    """
    latest_frame = None
    lock = asyncio.Lock()
    frame_event = asyncio.Event()
    _busy = False

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
                    elif data.get("type") == "voice":
                        voice_text = (data.get("data") or "").strip()
                        if voice_text:
                            logger.info(f"[SCENE] Voice command received: {voice_text}")
                            from App.core.contracts import SystemEvent as _SE
                            import uuid as _uuid
                            await bus.publish(_SE(
                                event_id=str(_uuid.uuid4()),
                                event_type="USER_COMMAND_RECEIVED",
                                payload={"text": voice_text},
                                priority=0,
                                timestamp=time.time(),
                            ))
                    elif data.get("type") == "gesture_command":
                        gesture = (data.get("data") or "").strip()
                        if gesture:
                            logger.info(f"[GESTURE] Gesture command received: {gesture}")
                            from App.core.contracts import SystemEvent as _SE
                            import uuid as _uuid
                            await bus.publish(_SE(
                                event_id=str(_uuid.uuid4()),
                                event_type="HAND_GESTURE_DETECTED",
                                payload={"gesture": gesture},
                                priority=0,
                                timestamp=time.time(),
                            ))

                if msg.get("bytes"):
                    async with lock:
                        latest_frame = msg["bytes"]
                    frame_event.set()

            except Exception as e:
                logger.error(f"Receiver error: {e}")
                remove_client(ws)
                break

    async def processor():
        nonlocal latest_frame, _busy

        while True:
            try:
                await asyncio.wait_for(frame_event.wait(), timeout=0.01)
            except asyncio.TimeoutError:
                pass
            frame_event.clear()

            frame_data = None
            async with lock:
                if latest_frame:
                    frame_data = latest_frame
                    latest_frame = None

            if not frame_data:
                continue

            if _busy:
                continue

            _busy = True
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
            finally:
                _busy = False

    await asyncio.gather(receiver(), processor())


async def send_detections(event):
    """EventBus handler: broadcasts detection results to all WebSocket clients.

    Subscribed to: "PERCEPTION_FRAME_READY"
    Called by: EventBus when PerceptionSystem publishes an event.

    Converts the TrackingState payload into a JSON message with:
    - detections: list of detected objects (id, label, confidence, bbox, depth, threat)
    - frame: frame dimensions
    - frame_ts: frame timestamp (epoch seconds) so frontend can detect staleness
    - perf: performance stats (FPS, inference time, depth time)

    The frontend uses this to render bounding boxes and overlays.
    """
    data = event.payload

    detections = [
        {
            "id": obj.object_id,
            "track_id": obj.track_id,
            "label": obj.class_name,
            "confidence": obj.confidence,
            "depth": obj.depth_norm,
            "bbox": obj.bbox,
            "threat_level": _threat_level(obj.depth_norm),
        }
        for obj in data.active_objects.values()
    ]

    message = {"type": "detections", "data": detections}
    message["frame"] = {
        "w": getattr(data, "frame_width", 0) or 0,
        "h": getattr(data, "frame_height", 0) or 0,
    }
    message["frame_ts"] = data.timestamp
    if getattr(data, "perf", None):
        message["perf"] = data.perf

    await broadcast_json(message)


# ---------------------------------------------------------------------------
# WebRTC (RTP) media ingress (/rtc)
# ---------------------------------------------------------------------------
# Active peer connections — kept for clean shutdown
pcs = set()

# Frame processing cadence — minimum sleep between processing attempts.
# With event-driven wake-up this only acts as a safety floor; the processor
# wakes immediately when a new frame arrives.
PROCESS_INTERVAL_SEC = 0.01


async def _process_rtc_track(track, perception, bus):
    """Process decoded frames from a WebRTC video track.

    Uses an asyncio.Event for instant wake-up: the processor does NOT poll
    on a fixed timer.  When the receiver gets a frame it signals the event,
    and the processor wakes immediately — eliminating the 50ms sleep that
    was the single biggest source of avoidable latency.

    Flow:
        track.recv() → frame.to_ndarray("bgr24") → numpy BGR array
            → signal event → processor wakes instantly
            → perception.process_frame() → SystemEvent
            → bus.publish() → EventBus fans out
    """
    latest_frame = None
    lock = asyncio.Lock()
    frame_event = asyncio.Event()     # signals "a new frame is ready"
    _frames_in = 0
    _frames_processed = 0
    _last_log = time.time()
    _busy = False                     # True while process_frame is running

    async def receiver():
        nonlocal latest_frame, _frames_in
        while True:
            try:
                frame = await track.recv()
                img = frame.to_ndarray(format="bgr24")
                async with lock:
                    latest_frame = img
                _frames_in += 1
                frame_event.set()     # wake the processor immediately
            except Exception as e:
                logger.warning(f"RTC receiver stopped: {type(e).__name__}: {e}")
                return

    async def processor():
        nonlocal latest_frame, _frames_processed, _busy
        while True:
            # Wait for a frame signal OR a short timeout (safety net)
            try:
                await asyncio.wait_for(frame_event.wait(), timeout=PROCESS_INTERVAL_SEC)
            except asyncio.TimeoutError:
                pass
            frame_event.clear()

            frame_data = None
            async with lock:
                if latest_frame is not None:
                    frame_data = latest_frame
                    latest_frame = None   # consume — latest-frame-wins

            if frame_data is None:
                continue

            # Skip if previous frame is still being processed (don't pile up)
            if _busy:
                continue

            _busy = True
            try:
                event = await asyncio.to_thread(perception.process_frame, frame_data)
                _frames_processed += 1
                await bus.publish(event)
            except Exception as e:
                logger.error(f"RTC processor error: {e}")
            finally:
                _busy = False

            # Performance log every 5 seconds
            now = time.time()
            if now - _last_log >= 5.0:
                logger.info(
                    f"[RTC] in={_frames_in / 5.0:.0f}/s  "
                    f"processed={_frames_processed / 5.0:.0f}/s"
                )
                _frames_in = 0
                _frames_processed = 0
                _last_log = now

    await asyncio.gather(receiver(), processor())


async def rtc_endpoint(ws: WebSocket, perception, bus):
    """WebRTC signaling endpoint — handles offer/answer/ICE exchange.

    Flow:
        1. Browser sends SDP offer → server creates answer
        2. ICE candidates exchanged for NAT traversal
        3. Once connected, browser streams video via RTP
        4. Server decodes frames and runs the perception pipeline

    The RTCPeerConnection handles the actual media streaming.
    This endpoint only handles the signaling (setup) phase.
    """
    await ws.accept()

    pc = RTCPeerConnection()
    pcs.add(pc)

    # When a video track arrives from the browser, start processing it
    @pc.on("track")
    def on_track(track):
        logger.info(f"RTC track received: {track.kind}")
        if track.kind == "video":
            asyncio.create_task(_process_rtc_track(track, perception, bus))

    # Send ICE candidates to the browser for connectivity
    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        if candidate:
            await ws.send_json({
                "type": "ice",
                "candidate": {
                    "candidate": candidate.candidate,
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex,
                },
            })

    # Clean up on connection failure/close
    @pc.on("connectionstatechange")
    async def on_connection_state_change():
        logger.info(f"RTC connection state: {pc.connectionState}")
        if pc.connectionState in ("failed", "closed"):
            await pc.close()
            pcs.discard(pc)

    try:
        # Process signaling messages from the browser
        while True:
            data = await ws.receive_json()

            if data.get("type") == "offer":
                # Set remote description (browser's offer)
                await pc.setRemoteDescription(
                    RTCSessionDescription(sdp=data["sdp"], type="offer")
                )
                # Create and send our answer
                answer = await pc.createAnswer()
                await pc.setLocalDescription(answer)
                await ws.send_json({
                    "type": "answer",
                    "sdp": pc.localDescription.sdp,
                })

            elif data.get("type") == "ice":
                # Add ICE candidate from the browser
                c = data.get("candidate") or {}
                if c.get("candidate"):
                    await pc.addIceCandidate(
                        RTCIceCandidate(
                            candidate=c["candidate"],
                            sdpMid=c.get("sdpMid"),
                            sdpMLineIndex=c.get("sdpMLineIndex"),
                        )
                    )

    except Exception as e:
        logger.error(f"RTC signaling error: {e}")
    finally:
        await pc.close()
        pcs.discard(pc)


async def close_all_peers():
    """Close all active WebRTC peer connections (called on shutdown)."""
    for pc in list(pcs):
        try:
            await pc.close()
        except Exception:
            pass
    pcs.clear()
