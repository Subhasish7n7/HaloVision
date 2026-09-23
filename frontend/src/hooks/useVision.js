import { useCallback, useEffect, useRef, useState } from "react"
import { socketService } from "../services/socket"
import { browserSpeak } from "../utils/browserSpeech"

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"

const DEFAULT_UI_CONFIG = {
  show_tracking_ids: true,
  show_confidence: false,
  box_colors: true,
  show_hand_tracking: true,
  show_finger_boxes: true,
  show_finger_labels: true,
  show_finger_tips: true,
  show_gesture: true,
  show_landmarks: false,
}

/**
 * Shared live-vision hook: WebSocket connection, detection state,
 * audio playback with interruption, mode/search/voice commands, and the
 * public UI config (tracking-ID / confidence / box-colour toggles).
 *
 * Returns:
 *  - connected          : socket connected
 *  - detections         : cleaned detection list from the backend
 *  - lastMessage        : text of the most recent audio message
 *  - lastMessageMeta    : { category, priority } of that message
 *  - uiConfig           : { show_tracking_ids, show_confidence, box_colors }
 *  - sendMode / sendSearch / sendVoice
 */
export function useVision({ mode = "camera" } = {}) {
  const [connected, setConnected] = useState(false)
  const [detections, setDetections] = useState([])
  const [lastMessage, setLastMessage] = useState("")
  const [lastMessageMeta, setLastMessageMeta] = useState({})
  const [uiConfig, setUiConfig] = useState(DEFAULT_UI_CONFIG)
  const [perf, setPerf] = useState(null)
  const [frameDims, setFrameDims] = useState(null)
  const [pathStatus, setPathStatus] = useState(null)

  const audioRef = useRef(null)
  const callbackRef = useRef(null)
  const trackMapRef = useRef(new Map())
  const anonIdRef = useRef(0)
  const gestureStateRef = useRef({
    wasOpenPalm: false,
    lastGestureSentTs: 0,
    stableFrameCount: 0,
    requiredStableFrames: 3,
  })

  useEffect(() => {
    // Public config for the overlay (tracking IDs / confidence / colors).
    // Admin edits show within the 5s backend refresh window of the announcer;
    // this fetch refreshes on every mount of a vision page.
    fetch(`${API_BASE}/api/ui-config`)
      .then((r) => (r.ok ? r.json() : null))
      .then((cfg) => {
        if (cfg) setUiConfig({ ...DEFAULT_UI_CONFIG, ...cfg })
      })
      .catch(() => {})

    const handleMessage = (data) => {
      setConnected(true)

      if (data?.type === "ui_config") {
        setUiConfig({ ...DEFAULT_UI_CONFIG, ...(data.data || {}) })
        return
      }

      if (data?.type === "speech_text") {
        // Backend TTS synthesis failed (e.g. network 403) and it fell back
        // to text — voice it locally in the browser instead.
        const text =
          typeof data?.data === "string"
            ? data.data
            : data?.text || ""
        if (text) {
          setLastMessage(text)
          browserSpeak(text, { priority: data?.priority ?? 1 })
        }
        return
      }

      if (data?.type === "audio") {
        if (data.text) {
          setLastMessage(data.text)
          setLastMessageMeta({
            category: data.category || "info",
            priority: data.priority ?? 1,
          })
        }

        // Preempt current playback for higher-priority speech
        if (data.interrupt && audioRef.current) {
          audioRef.current.pause()
          audioRef.current = null
        }

        if (data.audio) {
          const audio = new Audio("data:audio/wav;base64," + data.audio)
          audioRef.current = audio
          audio.play().catch(() => {})
        } else if (data.text) {
          // No synthesized blob on this message — use the browser voice.
          browserSpeak(data.text, { priority: data.priority ?? 1 })
        }
        return
      }

      if (data?.type === "path_status") {
        const ps = data.data
        if (ps && ps.status) {
          setPathStatus(ps)
        }
        return
      }

      let list = null
      if (Array.isArray(data)) {
        list = data
      } else if (Array.isArray(data?.detections)) {
        list = data.detections
      } else if (
        data?.type === "detections" &&
        Array.isArray(data?.data)
      ) {
        list = data.data
      }

      if (Array.isArray(list)) {
        if (data?.perf) {
          setPerf(data.perf)
        }
        // Backend's actual processed-frame size. Bbox coords are relative to
        // this frame, which can differ from video.videoWidth when WebRTC
        // renegotiates the encode resolution — using it fixes misaligned boxes.
        if (data?.frame?.w && data?.frame?.h) {
          setFrameDims({ w: data.frame.w, h: data.frame.h })
        }
        // Temporal smoothing: EMA blend per object id keeps confidence steady
        // and holds boxes briefly so low-threshold search mode doesn't flicker.
        const EMA = 0.35
        const HOLD_MS = 1200
        const now = Date.now()
        const seen = new Set()

        for (const raw of list) {
          const id = raw.id ?? `anon_${anonIdRef.current++}`
          const prev = trackMapRef.current.get(id)
          let confidence = raw.confidence ?? 0
          if (prev && prev.confidence > 0 && raw.confidence != null) {
            confidence = prev.confidence * (1 - EMA) + raw.confidence * EMA
          }

          // Tracking ID comes from the backend tracker (ByteTrack) — the
          // primary identity for colors, cooldowns and stable rendering.
          let track_id = raw.track_id
          if (track_id == null && typeof raw.id === "string" && raw.id.startsWith("track_")) {
            const parsed = Number(raw.id.slice(6))
            track_id = Number.isFinite(parsed) ? parsed : undefined
          }

          trackMapRef.current.set(id, {
            d: {
              id,
              track_id,
              class_name: raw.class_name || raw.label || "unknown",
              confidence,
              bbox: Array.isArray(raw.bbox) && raw.bbox.length === 4
                ? raw.bbox
                : [0, 0, 100, 100],
              depth: raw.depth ?? 0,
              threat_level: raw.threat_level ?? 0,
            },
            lastSeen: now,
          })
          seen.add(id)
        }

        for (const [id, entry] of trackMapRef.current) {
          if (!seen.has(id) && now - entry.lastSeen > HOLD_MS) {
            trackMapRef.current.delete(id)
          }
        }

        setDetections([...trackMapRef.current.values()].map((e) => e.d))
      }
    }

    callbackRef.current = handleMessage
    socketService.connect(handleMessage, () => setConnected(false))

    return () => {
      socketService.disconnect()
      callbackRef.current = null
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    socketService.sendMode(mode)
  }, [mode])

  const sendSearch = useCallback((text) => {
    socketService.sendSearch(text)
  }, [])

  const sendVoice = useCallback((text) => {
    socketService.sendVoice(text)
  }, [])

  const sendGestureCommand = useCallback((gesture) => {
    socketService.sendGestureCommand(gesture)
  }, [])

  return {
    connected,
    detections,
    lastMessage,
    lastMessageMeta,
    uiConfig,
    perf,
    frameDims,
    pathStatus,
    sendMode: socketService.sendMode,
    sendSearch,
    sendVoice,
    sendGestureCommand,
  }
}
