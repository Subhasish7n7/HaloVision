import { useEffect, useRef, useState } from "react"
import { motion } from "framer-motion"
import { Hand } from "lucide-react"

import { socketService } from "../services/socket"
import { HandTracker } from "../services/handTracker"
import { FINGER_ORDER } from "../utils/handGeometry"
import { gestureLabel } from "../utils/gestures"
import { coverBox, coverPoint } from "../utils/coverLayout"

// Inference cadence (MediaPipe video mode recomputes this often).
const INFER_MS = 33
// Paint cadence — the DOM updates at ~15fps, not per inference.
const PAINT_MS = 66
// Coordinate quantization for the change-signature check.
const Q = 1.5

const FINGER_COLORS = {
  thumb: "#facc15",
  index: "#38bdf8",
  middle: "#4ade80",
  ring: "#a78bfa",
  pinky: "#fb923c",
}

/**
 * HandOverlay — renders MediaPipe hand tracking results on top of the live
 * video inside CameraView.
 *
 * Performance model:
 *  - A rAF "infer" loop runs HandLandmarker.detectForVideo (GPU, local)
 *    and writes results to a ref — no React state.
 *  - A separate rAF "paint" loop (throttled to ~15fps) converts the latest
 *    results to pixels, and only triggers a re-render when the quantized
 *    signature actually changed.
 *  - Framer-motion boxes are static (no per-frame springs) — motion is used
 *    only for appear/disappear transitions.
 */
export function HandOverlay({ videoRef, containerRef, ui = {}, active = true }) {
  const enabled = active && ui.show_hand_tracking !== false

  const trackerRef = useRef(null)
  const latestRef = useRef([]) // raw hands (normalized) from the last infer
  const rafInferRef = useRef(null)
  const rafPaintRef = useRef(null)

  const [hands, setHands] = useState([]) // painted payload (pixel coords)
  const [status, setStatus] = useState("loading") // loading | ok | error
  const [statusError, setStatusError] = useState("")

  // Gesture debounce state for "Is the path clear?" feature.
  // Tracks whether open_palm was previously visible to detect transitions.
  const gestureStateRef = useRef({
    wasOpenPalm: false,
    stableFrameCount: 0,
    requiredStableFrames: 3,
    lastGestureSentTs: 0,
    gestureCooldownMs: 4000,
  })

  // ---- lifecycle --------------------------------------------------------
  useEffect(() => {
    if (!enabled) return
    let cancelled = false

    const tracker = new HandTracker({
      onStatus: (s) => {
        if (cancelled) return
        setStatus(s.ok ? "ok" : "error")
        if (!s.ok) setStatusError(s.error || "unavailable")
      },
    })
    trackerRef.current = tracker

    tracker.init().catch(() => {
      if (!cancelled) setStatus("error")
    })

    return () => {
      cancelled = true
      cancelAnimationFrame(rafInferRef.current)
      cancelAnimationFrame(rafPaintRef.current)
      latestRef.current = []
      setHands([])
      setStatus("loading")
      trackerRef.current = null
      tracker.stop()
    }
  }, [enabled])

  // ---- infer + paint loops ---------------------------------------------
  useEffect(() => {
    if (!enabled) return

    let lastInfer = 0
    let lastPaint = 0
    let lastSig = ""

    const infer = (now) => {
      rafInferRef.current = requestAnimationFrame(infer)
      if (now - lastInfer < INFER_MS) return
      lastInfer = now

      const tracker = trackerRef.current
      const video = videoRef.current
      if (!tracker?.isReady || !video) return
      latestRef.current = tracker.detect(video)
    }

    const paint = (now) => {
      rafPaintRef.current = requestAnimationFrame(paint)
      if (now - lastPaint < PAINT_MS) return
      lastPaint = now

      const video = videoRef.current
      const container = containerRef.current
      if (!video || !container) return

      const renderHands = latestRef.current
        .map((h) => ({
          handId: h.handId,
          label: gestureLabel(h.gesture?.name),
          handedness: h.handedness,
          palmSize: h.palmSize,
          fingers: Object.fromEntries(
            FINGER_ORDER.map((name) => {
              const f = h.fingers[name]
              const box = coverBox(f.bbox, video, container)
              const tip = coverPoint(f.tip.x, f.tip.y, video, container)
              return [
                name,
                {
                  ext: f.extended,
                  box,
                  tip,
                  lm: ui.show_landmarks
                    ? f.landmarks.map((p) => coverPoint(p.x, p.y, video, container))
                    : null,
                },
              ]
            })
          ),
        }))
        // Drop stale hands right here (tracker may still be in its grace period).
        .filter((h) =>
          Object.values(h.fingers).some((f) => f.box.width > 0 && f.box.height > 0)
        )

      const sig = JSON.stringify(
        renderHands.map((h) => [
          h.handId,
          Object.entries(h.fingers).map(([n, f]) => [
            n,
            f.ext ? 1 : 0,
            Math.round(f.box.left / Q),
            Math.round(f.box.top / Q),
            Math.round(f.box.width / Q),
            Math.round(f.box.height / Q),
            Math.round(f.tip.x / Q),
            Math.round(f.tip.y / Q),
          ]),
        ])
      )

      if (sig !== lastSig) {
        lastSig = sig
        setHands(renderHands)
      }

      // ---- Gesture command detection for "Is the path clear?" ----
      // Detect open_palm gesture and send to backend after stable detection.
      // Uses debounce: requires N consecutive frames with open_palm before sending,
      // then cools down to prevent repeated triggers.
      const gs = gestureStateRef.current
      const hasOpenPalm = renderHands.some(
        (h) => h.gesture?.name === "open_palm" && h.gesture?.confidence > 0.8
      )

      if (hasOpenPalm) {
        gs.stableFrameCount++
        if (
          gs.stableFrameCount >= gs.requiredStableFrames &&
          !gs.wasOpenPalm &&
          performance.now() - gs.lastGestureSentTs > gs.gestureCooldownMs
        ) {
          gs.wasOpenPalm = true
          gs.lastGestureSentTs = performance.now()
          try {
            socketService.sendGestureCommand("open_palm")
          } catch {
            // socket not connected — ignore
          }
        }
      } else {
        gs.stableFrameCount = 0
        gs.wasOpenPalm = false
      }
    }

    rafInferRef.current = requestAnimationFrame(infer)
    rafPaintRef.current = requestAnimationFrame(paint)

    return () => {
      cancelAnimationFrame(rafInferRef.current)
      cancelAnimationFrame(rafPaintRef.current)
    }
  }, [enabled, ui.show_landmarks, videoRef, containerRef])

  if (!enabled) return null

  const trackingFailed = status === "error"

  return (
    <>
      {/* STATUS / GESTURE CHIP */}
      <div className="absolute top-10 left-1/2 -translate-x-1/2 z-30 pointer-events-none">
        <div
          className={[
            "flex items-center gap-2 px-4 py-1.5 rounded-full border backdrop-blur-xl",
            trackingFailed
              ? "border-amber-400/30 bg-black/50"
              : "border-cyan-400/20 bg-black/50",
          ].join(" ")}
          title={statusError || "MediaPipe hand landmarks (local GPU)"}
        >
          <Hand
            size={14}
            className={
              trackingFailed ? "text-amber-400" : "text-cyan-300 animate-pulse"
            }
          />
          <span
            className={[
              "text-[10px] font-mono tracking-widest",
              trackingFailed ? "text-amber-400" : "text-cyan-200",
            ].join(" ")}
          >
            {trackingFailed
              ? "HAND TRACKING OFF"
              : `HAND ×${hands.length}${hands[0]?.label ? ` · ${hands[0].label}` : ""}`}
          </span>
        </div>
      </div>

      {/* HAND MARKUPS */}
      {hands.map((h) => (
        <motion.div
          key={`hand-${h.handId}`}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="absolute inset-0 pointer-events-none z-20"
        >
          {ui.show_landmarks &&
            Object.values(h.fingers).flatMap((f) =>
              (f.lm || []).map((p, i) => (
                <span
                  key={`lm-${h.handId}-${i}`}
                  className="absolute w-1 h-1 rounded-full bg-cyan-300/70"
                  style={{
                    left: p.x - 2,
                    top: p.y - 2,
                    boxShadow: "0 0 4px rgba(34,211,238,0.8)",
                  }}
                />
              ))
            )}

          {Object.entries(h.fingers).map(([name, f]) => {
            if (!f.tip || (f.tip.x === 0 && f.tip.y === 0)) return null
            const color = FINGER_COLORS[name]
            // Small precise box around the fingertip (nail region) only —
            // never the whole finger or hand. Padding stays 5-15px and
            // grows slightly with hand size.
            const pad = Math.max(5, Math.min(15, 8 + Math.round((h.palmSize || 0) * 30)))
            return (
              <motion.div
                key={`${h.handId}-${name}`}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.12, ease: "easeOut" }}
                className="absolute rounded-sm border"
                style={{
                  left: f.tip.x - pad,
                  top: f.tip.y - pad,
                  width: pad * 2,
                  height: pad * 2,
                  borderColor: `${color}cc`,
                  background: `${color}22`,
                  boxShadow: `0 0 6px ${color}55`,
                }}
              />
            )
          })}
        </motion.div>
      ))}
    </>
  )
}