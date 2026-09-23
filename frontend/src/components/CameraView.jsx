import { useEffect, useRef, useState, forwardRef, useImperativeHandle } from "react"
import { motion } from "framer-motion"

import {
  Radar,
  ShieldAlert,
  ScanLine,
} from "lucide-react"

import { socketService } from "../services/socket"
import { webrtcClient } from "../services/webrtc"
import { HandOverlay } from "./HandOverlay"

export const CameraView = forwardRef(function CameraView({
  detections = [],
  active = true,
  streaming = true,
  showHud = true,
  ui = null,
  frame = null,
}, ref) {

  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const containerRef = useRef(null)
  const isSendingRef = useRef(false)
  const animFrameRef = useRef(null)
  const streamRef = useRef(null)

  const [cameraReady, setCameraReady] = useState(false)
  const [cameraError, setCameraError] = useState("")
  const [rtcActive, setRtcActive] = useState(false)

  // Expose a capture() so a parent can freeze the current frame as a JPEG.
  useImperativeHandle(ref, () => ({
    capture: () => {
      const video = videoRef.current
      const canvas = canvasRef.current
      if (
        !video ||
        !canvas ||
        video.videoWidth === 0 ||
        video.videoHeight === 0
      ) {
        return null
      }
      canvas.width = video.videoWidth
      canvas.height = video.videoHeight
      const ctx = canvas.getContext("2d")
      if (!ctx) return null
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      return {
        dataUrl: canvas.toDataURL("image/jpeg", 0.85),
      }
    },
  }))

  // Reset camera state when active changes
  useEffect(() => {
    if (!active) {
      setCameraReady(false)
      setCameraError("")
    }
  }, [active])

  // CAMERA START
  useEffect(() => {
    if (!active) return     // If camera isn't active, do nothing.

    let mounted = true

    const startCamera = async () => {
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new DOMException(
            "Camera API unavailable. Camera access requires HTTPS when not on localhost. " +
            "Use HTTPS, run on localhost, or use Chrome flag: chrome://flags/#unsafely-treat-insecure-origin-as-secure",
            "NotSupportedError",
          )
        }

        const constraints = [
          {
            video: {
              facingMode: { ideal: "environment" },
              width: { ideal: 1280 },
              height: { ideal: 720 },
            },
            audio: false,
          },
          { video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false },
          { video: true, audio: false },
        ]

        let stream = null
        let lastErr = null
        for (const c of constraints) {
          try {
            stream = await navigator.mediaDevices.getUserMedia(c)
            break
          } catch (e) {
            lastErr = e
          }
        }
        if (!stream) throw lastErr

        if (!mounted) {
          stream.getTracks().forEach(t => t.stop())
          return
        }

        streamRef.current = stream

        const video = videoRef.current
        if (!video) {
          stream.getTracks().forEach(t => t.stop())
          return
        }

        video.srcObject = stream

        stream.getTracks().forEach((t) => {
          t.onended = () => {
            setCameraReady(false)
            setCameraError("Camera disconnected - reload to restart the feed")
          }
        })

        await new Promise((resolve, reject) => {
          video.onloadeddata = () => resolve()
          video.onerror = () => reject(new Error("Video load error"))
        })

        await video.play()

        if (mounted) {
          setCameraReady(true)
        }

        // Prefer WebRTC: stream the camera as RTP (no per-frame JPEG
        // round-trip). Negotiation is async — the legacy WebSocket fallback
        // keeps sending frames until the peer connection actually connects.
        webrtcClient
          .connect(stream)
          .then(() => {
            if (mounted) setRtcActive(true)
          })
          .catch(() => {
            if (mounted) setRtcActive(false)
          })
      } catch (err) {
        if (mounted) {
          const name = err?.name
          if (name === "NotAllowedError" || name === "SecurityError") {
            setCameraError("Camera permission denied - allow camera access in your browser")
          } else if (name === "NotFoundError" || name === "DevicesNotFoundError") {
            setCameraError("No camera found - connect a webcam and reload")
          } else if (name === "OverconstrainedError") {
            setCameraError("Camera cannot provide the requested video mode")
          } else if (name === "NotReadableError" || name === "TrackStartError") {
            setCameraError("Camera is in use by another app - close it and reload")
          } else if (name === "NotSupportedError") {
            setCameraError(
              "Camera unavailable over HTTP on this device. " +
              "Use HTTPS, run on localhost, or open Chrome flags and enable: " +
              "#unsafely-treat-insecure-origin-as-secure"
            )
          } else {
            setCameraError("Camera unavailable: " + (err?.message || "unknown error"))
          }
        }
      }
    }

    startCamera()

    return () => {
      mounted = false
      webrtcClient.stop()
      setRtcActive(false)
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop())
        streamRef.current = null
      }
      setCameraReady(false)
    }
  }, [active])  // Stop the camera after leaving the page

  // FRAME SENDING (legacy JPEG-over-WebSocket — only while WebRTC is off)
  useEffect(() => {
    if (!cameraReady || !active || !streaming || rtcActive) return

    const sendFrame = () => {
      if (!videoRef.current || !canvasRef.current || isSendingRef.current) {
        animFrameRef.current = requestAnimationFrame(sendFrame)
        return
      }

      const video = videoRef.current
      const canvas = canvasRef.current

      if (video.videoWidth === 0 || video.videoHeight === 0) {
        animFrameRef.current = requestAnimationFrame(sendFrame)
        return
      }

      const ctx = canvas.getContext("2d")
      if (!ctx) {
        animFrameRef.current = requestAnimationFrame(sendFrame)
        return
      }

      canvas.width = video.videoWidth
      canvas.height = video.videoHeight

      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

      isSendingRef.current = true

      canvas.toBlob((blob) => {
        isSendingRef.current = false
        if (blob) {
          blob.arrayBuffer().then(buffer => {
            socketService.sendFrame(buffer)   // frame send to backend
          })
        }
        animFrameRef.current = requestAnimationFrame(sendFrame)
      }, "image/jpeg", 0.7)
    }

    animFrameRef.current = requestAnimationFrame(sendFrame)

    return () => {
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current)
        animFrameRef.current = null
      }
      isSendingRef.current = false
    }
  }, [cameraReady, active, streaming, rtcActive])

  // THREAT COLOR
  const getThreatColor = (className) => {
    const lower = (className || "").toLowerCase()

    if (lower.includes("person") || lower.includes("human")) {
      return "border-yellow-400 text-yellow-400"
    }

    if (
      lower.includes("car") ||
      lower.includes("vehicle") ||
      lower.includes("truck") ||
      lower.includes("bus") ||
      lower.includes("motorcycle")
    ) {
      return "border-red-400 text-red-400"
    }

    return "border-cyan-400 text-cyan-400"
  }

  // Accessible per-track-ID palette — same ID always maps to the same color
  // while it is active; distinct IDs get distinct colors even for the same
  // class. Visual identity comes from the backend ByteTrack IDs only.
  const TRACK_PALETTE = [
    { border: "38bdf8", text: "#e0f2fe", glow: "rgba(56,189,248,0.45)" },   // sky
    { border: "a78bfa", text: "#ede9fe", glow: "rgba(167,139,250,0.45)" },  // violet
    { border: "4ade80", text: "#dcfce7", glow: "rgba(74,222,128,0.45)" },   // green
    { border: "fb923c", text: "#ffedd5", glow: "rgba(251,146,60,0.45)" },   // orange
    { border: "f472b6", text: "#fce7f3", glow: "rgba(244,114,182,0.45)" },  // pink
    { border: "22d3ee", text: "#cffafe", glow: "rgba(34,211,238,0.45)" },   // cyan
    { border: "facc15", text: "#fefce8", glow: "rgba(250,204,21,0.45)" },   // yellow
    { border: "60a5fa", text: "#dbeafe", glow: "rgba(96,165,250,0.45)" },   // blue
    { border: "f87171", text: "#fee2e2", glow: "rgba(248,113,113,0.45)" },  // red
    { border: "2dd4bf", text: "#ccfbf1", glow: "rgba(45,212,191,0.45)" },   // teal
  ]
  const segmentColor = (trackId) =>
    TRACK_PALETTE[Math.abs(Number(trackId) || 0) % TRACK_PALETTE.length]

  // Accessible UI config at component scope (used for detections + hand overlay).
  const uiCfg = ui || {}

  // Compute detection box positions with object-fit: cover math
  const computeBoxStyle = (bbox) => {
    const [x1, y1, x2, y2] = bbox || [0, 0, 100, 100]
    const video = videoRef.current
    const container = containerRef.current

    // bbox coords are relative to the frame the backend actually processed.
    // Prefer those dims over video.videoWidth so WebRTC resolution
    // renegotiation can't shift the boxes away from the person/object.
    const vw = frame?.w || video?.videoWidth || 640
    const vh = frame?.h || video?.videoHeight || 480

    if (!container) {
      // Fallback: percentage of the actual frame dimensions
      return {
        left: `${(x1 / vw) * 100}%`,
        top: `${(y1 / vh) * 100}%`,
        width: `${((x2 - x1) / vw) * 100}%`,
        height: `${((y2 - y1) / vh) * 100}%`,
      }
    }

    const cw = container.clientWidth
    const ch = container.clientHeight

    const scale = Math.max(cw / vw, ch / vh)
    const displayedW = vw * scale
    const displayedH = vh * scale
    const offsetX = (cw - displayedW) / 2
    const offsetY = (ch - displayedH) / 2

    return {
      left: `${x1 * scale + offsetX}px`,
      top: `${y1 * scale + offsetY}px`,
      width: `${(x2 - x1) * scale}px`,
      height: `${(y2 - y1) * scale}px`,
    }
  }

  return (

    <div
      ref={containerRef}
      className="
        absolute inset-0
        w-full h-full
        overflow-hidden
        bg-black
      "
    >

      {/* VIDEO */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className="
          absolute inset-0
          w-full h-full
          object-cover
        "
      />

      {/* CAMERA ERROR */}
      {cameraError && (

        <div
          className="
            absolute inset-0
            flex items-center justify-center
            bg-black z-50
          "
        >

          <div className="text-center">

            <ShieldAlert
              size={50}
              className="
                text-red-400
                mx-auto mb-4
              "
            />

            <p className="text-red-400">
              {cameraError}
            </p>

          </div>

        </div>

      )}

      {/* LOADING */}
      {!cameraReady && !cameraError && (

        <div
          className="
            absolute inset-0
            flex items-center justify-center
            bg-black z-40
          "
        >

          <motion.div
            animate={{ rotate: 360 }}
            transition={{
              duration: 1,
              repeat: Infinity,
              ease: "linear",
            }}
            className="
              w-16 h-16 rounded-full
              border-2 border-transparent
              border-t-gold
            "
          />

        </div>

      )}

      {/* DETECTIONS */}
      {detections.map((d, i) => {

        const className =
          d.class_name ||
          d.label ||
          "unknown"

        const trackId = d.track_id
        const hasTrackId = trackId != null

        // Admin toggles: per-ID colors override the threat-based ones.
        const colorsOn = uiCfg.box_colors !== false && hasTrackId
        const trackColor = colorsOn ? segmentColor(trackId) : null
        const borderColor = trackColor ? `#${trackColor.border}` : undefined

        const threatClass =
          trackColor ? "" : getThreatColor(className)

        return (

          <motion.div
            key={d.id || i}
            initial={{
              opacity: 0,
              scale: 0.95,
            }}
            animate={{
              opacity: 1,
              scale: 1,
            }}
            transition={{
              duration: 0.18,
              ease: "easeOut",
            }}
            className="
              absolute
              rounded-lg
              overflow-hidden
            "

            style={{
              pointerEvents: "none",
              ...computeBoxStyle(d.bbox),
            }}
          >

            <div
              className={`
                absolute inset-0
                border-2
                bg-black/15
                ${trackColor ? "" : threatClass}
              `}
              style={
                trackColor
                  ? {
                      borderColor,
                      boxShadow: `0 0 14px ${trackColor.glow}`,
                    }
                  : undefined
              }
            />

            <div
              className={`
                absolute -top-0.5 left-1.5
                flex items-center gap-1.5
                px-2 py-0.5
                rounded-md
                text-[11px] font-mono font-semibold
                backdrop-blur-md
                border
                border-white/10
              `}
              style={{
                background: trackColor ? "rgba(0,0,0,0.7)" : "rgba(0,0,0,0.72)",
                color: trackColor ? trackColor.text : undefined,
                boxShadow: trackColor ? `0 0 10px ${trackColor.glow}` : undefined,
              }}
            >

              <span
                className="inline-block w-1.5 h-1.5 rounded-full"
                style={{
                  background: trackColor ? `#${trackColor.border}` : undefined,
                }}
              />

              <span>{className}</span>

              {uiCfg.showTrackingIds !== false && hasTrackId && (
                <span className="text-white/85">
                  ID: {trackId}
                </span>
              )}

              {uiCfg.showConfidence && d.confidence != null && (
                <span className="opacity-60">
                  {Math.round(d.confidence * 100)}%
                </span>
              )}

            </div>

          </motion.div>

        )

      })}

      {showHud && (
        <>
      {/* TOP LEFT HUD */}
      <div
        className="
          absolute top-10 left-4
          flex items-center gap-2
          px-4 py-2
          rounded-full
          bg-black/50
          backdrop-blur-xl
          border border-white/10
        "
      >

        <Radar
          size={16}
          className="text-gold"
        />

        <span
          className="
            text-xs text-red-500
            font-mono
            animate-pulse
          "
        >
          LIVE CAMERA
        </span>

      </div>

      {/* TOP RIGHT */}
      <div
        className="
          absolute top-10 right-4
          flex items-center gap-2
          px-4 py-2
          rounded-full
          bg-black/50
          backdrop-blur-xl
          border border-white/10
        "
      >

        <ShieldAlert
          size={16}
          className={
            detections.length > 0
              ? "text-green-400"
              : "text-white/40"
          }
        />

        <span
          className={`
            text-xs font-mono
            ${
              detections.length > 0
                ? "text-green-400"
                : "text-white/40"
            }
          `}
        >

          {detections.length}
          {" "}
          DETECTED

        </span>

      </div>

      {/* SCAN LINE */}
      <motion.div
        animate={{
          top: ["0%", "100%"],
        }}
        transition={{
          duration: 4,
          repeat: 3,
          ease: "linear",
        }}
        className="
          absolute left-0 right-0
          h-px
          bg-gradient-to-r
          from-transparent
          via-gold
          to-transparent
          opacity-50
        "
      />

      {/* BOTTOM STATUS */}
      <div
        className="
          absolute bottom-4 left-4
          flex items-center gap-2
          px-4 py-2
          rounded-full
          bg-black/50
          backdrop-blur-xl
          border border-white/10
        "
      >

        <ScanLine
          size={14}
          className="text-green-400"
        />

        <span
          className="
            text-xs text-green-400
            font-mono
          "
        >
          SCANNING ACTIVE
        </span>

      </div>
        </>
      )}

      {/* HIDDEN CANVAS */}
      <canvas
        ref={canvasRef}
        className="hidden"
      />

      {/* HAND / FINGER TRACKING (MediaPipe, local inference) */}
      <HandOverlay
        videoRef={videoRef}
        containerRef={containerRef}
        ui={uiCfg}
        active={active && cameraReady}
      />

    </div>
  )
})
