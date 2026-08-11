"""Per-tracking-ID TTS announcement system.

Authoritative cooldown state lives here (backend), keyed by
``"{class_name}:{track_id}"`` so every tracked object gets its own
60-second announcement window and independent knowledge of its own color
and identity. Announcements flow through a small priority queue and are
synthesized with edge-tts, then streamed to clients over the WebSocket as
``{"type": "audio", ...}`` messages (the frontend already plays these).

Configuration comes from admin-editable FeatureFlags (on/off toggles) and
SystemSettings (numeric knobs) seeded in migrations.
"""

import asyncio
import base64
import heapq
import io
import itertools
import logging
import time

import edge_tts

from App.api import models
from App.api.database import SessionLocal
from App.api import websocket
from App.core.safety import DEPTH_VERY_CLOSE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TTS priority (lower = more important, announced first).
# Ordered per product spec: Person > Vehicle > Obstacle > Stairs > Door >
# Chair > Table > Bottle > Other.
# ---------------------------------------------------------------------------
CLASS_PRIORITY = {
    "person": 1,
    "human": 1,
    "car": 2, "bus": 2, "truck": 2, "motorcycle": 2,
    "bicycle": 2, "train": 2, "boat": 2, "airplane": 2,
    "obstacle": 3,
    "stairs": 4, "staircase": 4, "steps": 4,
    "door": 5,
    "chair": 6,
    "table": 7, "dining table": 7, "couch": 7,
    "bottle": 8, "cup": 8,
}
DEFAULT_PRIORITY = 9

_FLAG_KEYS = ("tts_announcements", "tts_priority", "tts_duplicate_classes")

_SETTING_DEFAULTS = {
    "tts_cooldown_sec": 60.0,   # seconds between announcements per track ID
    "tts_queue_max": 5,         # max pending announcements
    "tts_grace_sec": 5.0,       # object can vanish this long without resetting cooldown
    "tts_id_expiry_sec": 120.0, # stale track keys removed after this
    "tts_speed": 1.0,           # speech rate multiplier
    "tts_voice": "en-US-AriaNeural",
}

_SIDE_THRESHOLD = 0.25
_CONFIG_TTL = 5.0


class DetectionTTSAnnouncer:
    """Subscribes to PERCEPTION_FRAME_READY and announces new objects via
    per-track-ID cooldowns, a bounded priority queue, and edge-tts audio
    pushed over the WebSocket."""

    def __init__(self):
        self._cooldowns = {}   # "class:track_id" -> {"last_announced": float, "last_seen": float}
        self._queued = set()   # keys currently sitting in the pending queue
        self._queue = []       # heap of (priority, seq, key, text)
        self._seq = itertools.count()
        self._cache = {}
        self._cache_ts = 0.0
        self._worker_task = None

    # ------------------------------------------------------------------
    # LIFECYCLE
    # ------------------------------------------------------------------
    async def start(self):
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("[DetectionTTS] announcer started")

    # ------------------------------------------------------------------
    # CONFIG (cached DB reads - refreshed every few seconds)
    # ------------------------------------------------------------------
    def _config(self):
        now = time.time()
        cache = self._cache
        if cache and now - self._cache_ts < _CONFIG_TTL:
            return cache

        cfg = {
            "tts_cooldown_sec": _SETTING_DEFAULTS["tts_cooldown_sec"],
            "tts_queue_max": _SETTING_DEFAULTS["tts_queue_max"],
            "tts_grace_sec": _SETTING_DEFAULTS["tts_grace_sec"],
            "tts_id_expiry_sec": _SETTING_DEFAULTS["tts_id_expiry_sec"],
            "tts_speed": _SETTING_DEFAULTS["tts_speed"],
            "tts_voice": _SETTING_DEFAULTS["tts_voice"],
            "tts_announcements": True,
            "tts_priority": True,
            "tts_duplicate_classes": True,
        }

        try:
            db = SessionLocal()
            try:
                flags = {
                    f.key: f.enabled
                    for f in db.query(models.FeatureFlag)
                    .filter(models.FeatureFlag.key.in_(_FLAG_KEYS))
                    .all()
                }
                for key in _FLAG_KEYS:
                    cfg[key] = flags.get(key, True)

                rows = db.query(models.SystemSetting).all()
                for r in rows:
                    if r.key in ("tts_cooldown_sec", "tts_grace_sec", "tts_id_expiry_sec"):
                        try:
                            cfg[r.key] = max(1.0, float(r.value or 0))
                        except (TypeError, ValueError):
                            pass
                    elif r.key == "tts_queue_max":
                        try:
                            cfg[r.key] = max(1, min(20, int(float(r.value or 0))))
                        except (TypeError, ValueError):
                            pass
                    elif r.key == "tts_speed":
                        try:
                            cfg[r.key] = max(0.5, min(2.5, float(r.value or 1)))
                        except (TypeError, ValueError):
                            pass
                    elif r.key == "tts_voice":
                        cfg[r.key] = (r.value or "en-US-AriaNeural").strip() or "en-US-AriaNeural"
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[DetectionTTS] config load failed: {e}")

        self._cache = cfg
        self._cache_ts = now
        return cfg

    # ------------------------------------------------------------------
    # EVENT HANDLER (per processed frame)
    # ------------------------------------------------------------------
    async def handle_frame(self, event):
        cfg = self._config()
        now = event.payload.timestamp

        for obj in event.payload.active_objects.values():
            track_id = getattr(obj, "track_id", -1)
            if track_id is None or track_id < 0:
                continue

            key = f"{obj.class_name.lower()}:{track_id}"
            state = self._cooldowns.setdefault(
                key, {"last_announced": 0.0, "last_seen": now}
            )
            state["last_seen"] = now

            if not cfg["tts_announcements"]:
                continue
            if key in self._queued:
                continue
            if state["last_announced"] and now - state["last_announced"] < cfg["tts_cooldown_sec"]:
                continue
            if not cfg["tts_duplicate_classes"] and self._class_pending(obj.class_name.lower()):
                continue

            self._enqueue(obj, key, cfg)

        self._cleanup(cfg, now)

    def _class_pending(self, class_name):
        prefix = f"{class_name}:"
        return any(k.startswith(prefix) for k in self._queued)

    # ------------------------------------------------------------------
    # QUEUE
    # ------------------------------------------------------------------
    def _enqueue(self, obj, key, cfg):
        text = self._text_for(obj)
        priority = self._priority_for(obj.class_name.lower(), cfg["tts_priority"])
        seq = next(self._seq)

        heapq.heappush(self._queue, (priority, seq, key, text))
        self._queued.add(key)

        # Reserve the cooldown immediately so queue waits/thrash never allow
        # repeated announcements for the same track within the window.
        self._cooldowns[key]["last_announced"] = time.time()

        max_q = int(cfg["tts_queue_max"])
        if len(self._queue) > max_q:
            # Drop the least important pending item (highest priority number,
            # oldest first). Its cooldown reservation is kept so it does not
            # re-spam on the next frame.
            worst = max(self._queue, key=lambda item: (item[0], -item[1]))
            self._queue.remove(worst)
            heapq.heapify(self._queue)
            self._queued.discard(worst[2])
            logger.info(f"[DetectionTTS] queue full - dropped pending '{worst[3]}'")

    def _text_for(self, obj):
        words = (obj.class_name or "object").replace("_", " ").strip()
        name = words[0].upper() + words[1:]
        side = ""
        offset = obj.horizontal_offset_norm
        if offset is not None:
            if offset < -_SIDE_THRESHOLD:
                side = " on your left"
            elif offset > _SIDE_THRESHOLD:
                side = " on your right"
            else:
                side = " ahead"
        close = ""
        if obj.depth_norm and obj.depth_norm >= DEPTH_VERY_CLOSE:
            close = ", very close"
        return f"{name} detected{side}{close}."

    @staticmethod
    def _priority_for(class_name: str, enabled: bool) -> int:
        if not enabled:
            return DEFAULT_PRIORITY
        return CLASS_PRIORITY.get(class_name, DEFAULT_PRIORITY)

    # ------------------------------------------------------------------
    # CLEANUP (bounded state, ID reuse safety)
    # ------------------------------------------------------------------
    def _cleanup(self, cfg, now):
        if not self._cooldowns:
            return
        keep = max(cfg["tts_id_expiry_sec"], cfg["tts_cooldown_sec"] + cfg["tts_grace_sec"])
        stale = [
            key for key, st in self._cooldowns.items()
            if now - st["last_seen"] > keep
        ]
        for key in stale:
            del self._cooldowns[key]

    # ------------------------------------------------------------------
    # WORKER (synthesize + broadcast)
    # ------------------------------------------------------------------
    async def _worker(self):
        logger.info("[DetectionTTS] worker loop running")
        while True:
            await asyncio.sleep(0.15)
            item = None
            if self._queue:
                item = heapq.heappop(self._queue)
                self._queued.discard(item[2])
            if not item:
                continue
            _priority, _seq, key, text = item
            try:
                await self._synth_and_broadcast(text)
            except Exception as e:
                logger.exception(f"[DetectionTTS] speech failed for {key}: {e}")
                # Graceful fallback: show the announcement as text so the UI
                # (and future synthesis) can still surface it.
                try:
                    await websocket.broadcast_json({"type": "speech_text", "data": text})
                except Exception:
                    pass

    async def _synth_and_broadcast(self, text):
        cfg = self._config()
        voice = cfg["tts_voice"]
        kwargs = {}
        speed = float(cfg["tts_speed"])
        if speed != 1.0:
            kwargs["rate"] = f"{int(round((speed - 1) * 100)):+d}%"

        buf = io.BytesIO()
        communicate = edge_tts.Communicate(text=text, voice=voice, **kwargs)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])

        audio_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        await websocket.broadcast_json({
            "type": "audio",
            "text": text,
            "audio": audio_b64,
            "category": "detection",
            "priority": 1,
            "interrupt": False,
        })
        logger.info(f"[DetectionTTS] announced: {text}")