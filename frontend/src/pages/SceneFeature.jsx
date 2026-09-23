import { useCallback, useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import {
  ArrowLeft,
  Camera,
  CheckCircle2,
  Loader2,
  Lock,
  RefreshCw,
  ScanEye,
  Sparkles,
  X,
  AlertTriangle,
  Volume2,
} from "lucide-react"
import HUDOverlay from "../components/HUDOverlay"
import { CameraView } from "../components/CameraView"
import { useTTS } from "../context/TTSContext"
import TTSButton from "../components/TTSButton"

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"

const ESTIMATED_SECONDS = 9

// Simulated stage map. These stages keep the user informed while the real
// backend request runs; progress pauses at 90% and only reaches 100% when the
// actual Vision LLM response arrives.
const STAGES = [
  { label: "Preparing Image…", t0: 0, p0: 2, t1: 1.2, p1: 14 },
  { label: "Uploading Image…", t0: 1.2, p0: 16, t1: 3.0, p1: 30 },
  { label: "Analyzing Scene…", t0: 3.0, p0: 34, t1: 5.2, p1: 56 },
  { label: "Understanding Objects…", t0: 5.2, p0: 58, t1: 7.2, p1: 78 },
  { label: "Generating Description…", t0: 7.2, p0: 80, t1: 9.0, p1: 90 },
]
const PAUSE_PCT = 90
const RESULT_STAGE = "Finalizing…"

// Module-scope memory: preserves the last session when the user leaves and
// returns (Camera Paused -> Refresh), so Home does not auto-restart.
const sessionMemory = { paused: false, lastResult: null }

function readToken() {
  return (
    localStorage.getItem("halo_token") ||
    sessionStorage.getItem("halo_token") ||
    ""
  )
}

function dataUrlToBlob(dataUrl) {
  return fetch(dataUrl).then((r) => r.blob())
}

export default function SceneFeature() {
  const { enabled: ttsEnabled, announce } = useTTS()
  const cameraRef = useRef(null)
  const startedAtRef = useRef(0)
  const controllerRef = useRef(null)
  const audioRef = useRef(null)
  const audioUrlRef = useRef(null)
  const spokenKeyRef = useRef(null)
  const busyRef = useRef(false)

  const [phase, setPhase] = useState("capture")
  const [frozen, setFrozen] = useState(null)
  const [progress, setProgress] = useState(0)
  const [stageLabel, setStageLabel] = useState(STAGES[0].label)
  const [secondsLeft, setSecondsLeft] = useState(ESTIMATED_SECONDS)
  const [locked, setLocked] = useState(false)
  const [cancelable, setCancelable] = useState(false)
  const [ripple, setRipple] = useState(false)
  const [showPanel, setShowPanel] = useState(false)
  const [errorMsg, setErrorMsg] = useState("")
  const [result, setResult] = useState(null)

  // Restore previous session state on mount
  useEffect(() => {
    if (sessionMemory.paused && sessionMemory.lastResult) {
      setPhase("paused")
      setResult(sessionMemory.lastResult)
      setFrozen(sessionMemory.lastResult.captureUrl || null)
      return
    }
    // No prior result — go straight to capture
    sessionMemory.paused = false
    sessionMemory.lastResult = null
    setPhase("capture")
  }, [])

  // Remember the session when leaving the page (fetch cleanup + pause).
  useEffect(() => {
    return () => {
      sessionMemory.paused = true
      if (frozen) sessionMemory.lastResult = { ...result, captureUrl: frozen }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frozen, result])

  // Human-friendly elapsed helpers
  const elapsed = () => (Date.now() - startedAtRef.current) / 1000

  // Progress + countdown + nav-lock ticker while processing.
  useEffect(() => {
    if (phase !== "processing") return

    const tick = () => {
      const t = elapsed()
      let pct = 0
      let label = STAGES[0].label

      for (const s of STAGES) {
        if (t >= s.t0) {
          label = s.label
          pct =
            t >= s.t1 ? s.p1 : s.p0 + ((t - s.t0) / (s.t1 - s.t0)) * (s.p1 - s.p0)
        }
      }
      // Pause at 90% until the real response arrives (never fake 100%).
      if (pct >= PAUSE_PCT) pct = PAUSE_PCT

      setProgress(Math.min(99, Math.round(pct)))
      setStageLabel(label)
      setSecondsLeft(Math.max(0, ESTIMATED_SECONDS - Math.floor(t)))
      setLocked(t < 3)
      setCancelable(t >= 3)
    }

    const interval = setInterval(tick, 120)
    return () => clearInterval(interval)
  }, [phase])

  const ttsBusyRef = useRef(false)

  const speak = useCallback(async (text) => {
    if (!text || ttsBusyRef.current) return
    if (!ttsEnabled) return
    ttsBusyRef.current = true
    try {
      if (audioRef.current) audioRef.current.pause()
      if (audioUrlRef.current) {
        URL.revokeObjectURL(audioUrlRef.current)
        audioUrlRef.current = null
      }

      const res = await fetch(`${API_BASE}/scene/speak`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${readToken()}`,
        },
        body: JSON.stringify({ speech_text: text }),
      })
      if (!res.ok) throw new Error("speech failed")

      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      audioUrlRef.current = url
      const audio = new Audio(url)
      audioRef.current = audio
      audio.play().catch(() => {})
      audio.onended = () => {
        if (audioUrlRef.current === url) {
          URL.revokeObjectURL(url)
          audioUrlRef.current = null
        }
      }
    } catch {
      // Non-fatal: fall back to browser TTS for the description text
      announce(text, { priority: 2 })
    } finally {
      ttsBusyRef.current = false
    }
  }, [ttsEnabled, announce])

  const runAnalysis = useCallback(async (blob, captureUrl) => {
    if (busyRef.current) return
    busyRef.current = true
    controllerRef.current = new AbortController()

    try {
      const form = new FormData()
      form.append("file", blob, "capture.jpg")

      const res = await fetch(`${API_BASE}/scene/analyze`, {
        method: "POST",
        headers: { Authorization: `Bearer ${readToken()}` },
        body: form,
        signal: controllerRef.current.signal,
      })

      if (!res.ok) {
        throw new Error(`analysis failed (${res.status})`)
      }

      const data = await res.json()

      const completed = {
        ...data,
        capture: captureUrl || null,
        id: Date.now(),
      }
      sessionMemory.lastResult = completed
      setResult(completed)
      setProgress(100)
      setStageLabel(RESULT_STAGE)
      setLocked(false)
      setPhase("completed")
      announce("Scene description ready.", { priority: 1 })
      // Auto-speak the description exactly once.
      spokenKeyRef.current = completed.id
      setTimeout(() => {
        if (spokenKeyRef.current === completed.id) speak(completed.speech_text)
      }, 800)
    } catch (err) {
      if (err.name === "AbortError") {
        setErrorMsg("Analysis cancelled")
        announce("Analysis cancelled.", { priority: 1 })
      } else {
        setErrorMsg("Analysis Failed")
        announce("Unable to describe the scene.", { priority: 1 })
      }
      setLocked(false)
      setPhase("error")
    } finally {
      busyRef.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  })

  const handleCapture = useCallback(async () => {
    if (busyRef.current || phase === "processing" || phase === "completed") return

    const shot = cameraRef.current?.capture?.()
    if (!shot) {
      announce("Camera not ready yet. Please wait a moment and try again.", { priority: 2 })
      return
    }
    announce("Describing scene.", { priority: 1 })

    // Ripple on capture
    setRipple(true)
    setTimeout(() => setRipple(false), 800)

    setFrozen(shot.dataUrl)
    setErrorMsg("")
    setResult(null)
    setShowPanel(false)
    setProgress(0)
    setStageLabel("Preparing Image…")
    setSecondsLeft(ESTIMATED_SECONDS)
    setLocked(true)
    setCancelable(false)
    setPhase("processing")
    startedAtRef.current = Date.now()
    spokenKeyRef.current = null

    const blob = await dataUrlToBlob(shot.dataUrl)
    runAnalysis(blob, shot.dataUrl)
  }, [phase, runAnalysis])

  const cancelAnalysis = useCallback(() => {
    if (!cancelable) return
    controllerRef.current?.abort()
  }, [cancelable])

  const captureAgain = useCallback(() => {
    if (audioRef.current) audioRef.current.pause()
    busyRef.current = false
    setResult(null)
    setErrorMsg("")
    setFrozen(null)
    setShowPanel(false)
    setProgress(0)
    setLocked(false)
    setStageLabel("Preparing Image…")
    setSecondsLeft(ESTIMATED_SECONDS)
    setPhase("capture")
    spokenKeyRef.current = null
  }, [])

  const refreshSession = useCallback(() => {
    // Restart the whole engine session + clear previous frame.
    if (audioRef.current) audioRef.current.pause()
    busyRef.current = false
    sessionMemory.paused = false
    sessionMemory.lastResult = null
    setResult(null)
    setFrozen(null)
    setErrorMsg("")
    setShowPanel(false)
    setProgress(0)
    setLocked(false)
    setPhase("capture")
    spokenKeyRef.current = null
  }, [])

  const togglePanel = useCallback(() => {
    if (!locked) setShowPanel((v) => !v)
  }, [locked])

  // Escape / navigation lock: blocked entirely while locked.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault()
        togglePanel()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [togglePanel])

  const objects = result?.objects || []
  const cameraActive = phase === "capture"
  const showFrozen = phase === "processing" || phase === "error" || phase === "completed"

  return (
    <HUDOverlay title="SCENE DESCRIPTION — SMART CONTEXT ANALYSIS">
      <div className="relative w-full h-screen overflow-hidden bg-black">
        {/* LIVE OR FROZEN CAMERA */}
        <CameraView
          ref={cameraRef}
          detections={[]}
          active={cameraActive}
          streaming={false}
          showHud={false}
        />

        {/* FROZEN CAPTURE OVERLAY */}
        {frozen && showFrozen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="absolute inset-0 z-20"
          >
            <img src={frozen} alt="Captured frame" className="w-full h-full object-cover" />
            {phase === "processing" && <div className="absolute inset-0 backdrop-blur-md bg-black/40" />}
          </motion.div>
        )}

        {/* BACK — disabled while navigation is locked */}
        <Link
          to="/home"
          onClick={(e) => locked && e.preventDefault()}
          className={`absolute top-20 left-6 z-50 flex items-center gap-2 px-4 py-2.5 rounded-full backdrop-blur-2xl border transition-all duration-200 cursor-pointer ${
            locked
              ? "border-white/10 bg-black/40 text-white/30 pointer-events-none"
              : "border-white/15 bg-black/60 text-white/70 hover:text-gold hover:border-gold/30"
          }`}
        >
          <ArrowLeft size={18} />
          <span className="text-sm font-medium">Back</span>
        </Link>

        {/* TTS Toggle */}
        <div className="absolute top-20 right-6 z-50">
          <TTSButton />
        </div>
        {locked && (
          <div className="absolute top-28 left-6 z-50 flex items-center gap-2 px-3 py-1.5 rounded-full border border-gold/20 bg-black/60 backdrop-blur-xl">
            <Lock size={12} className="text-gold" />
            <span className="text-[10px] font-mono tracking-widest text-gold/70">LINKED SEA — NAVIGATION LOCKED</span>
          </div>
        )}

        {/* CAMERA PAUSED STATE (returning from Home without Refresh) */}
        {phase === "paused" && (
          <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/80">
            <div className="text-center px-6">
              <div className="w-16 h-16 mx-auto mb-5 rounded-full border border-white/10 bg-white/5 flex items-center justify-center">
                <Camera size={26} className="text-white/50" />
              </div>
              <h2 className="font-poppins text-2xl font-bold text-white mb-2">Camera Paused</h2>
              <p className="text-white/50 text-sm mb-8 max-w-xs mx-auto">
                Your previous session is preserved. Press Refresh to start a new live session.
              </p>
              <button
                onClick={refreshSession}
                aria-label="Refresh camera session"
                className="flex items-center gap-2 px-6 py-3 rounded-full text-sm font-semibold text-black bg-gradient-to-r from-gold-dark to-gold hover:brightness-110 hover:-translate-y-0.5 active:scale-95 transition-all duration-200 shadow-[0_8px_28px_rgba(255,179,71,0.35)]"
              >
                <RefreshCw size={16} />
                Refresh
              </button>
            </div>
          </div>
        )}

        {/* CAPTURE BUTTON — phone-style, bottom center */}
        {(phase === "capture" || phase === "live") && (
          <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-50 flex flex-col items-center gap-3">
            {phase === "capture" && (
              <span className="text-[10px] font-mono tracking-widest text-white/40">
                POINT &amp; CAPTURE A FRAME
              </span>
            )}

            <button
              onClick={handleCapture}
              disabled={busyRef.current}
              className="group relative w-20 h-20 rounded-full flex items-center justify-center transition-transform duration-200 active:scale-90 hover:scale-105 disabled:opacity-40"
              aria-label="Capture frame"
            >
              {/* Ripple after capture */}
              <AnimatePresence>
                {ripple && (
                  <motion.span
                    key="ripple"
                    initial={{ scale: 0.8, opacity: 0.7 }}
                    animate={{ scale: 2.2, opacity: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.7 }}
                    className="absolute inset-0 rounded-full border-4 border-gold/50 pointer-events-none"
                  />
                )}
              </AnimatePresence>

              {/* Outer ring */}
              <span className="absolute inset-0 rounded-full border-[5px] border-white/90 shadow-[0_8px_30px_rgba(0,0,0,0.5)]" />

              {/* Inner dark circle */}
              <span className="absolute inset-[10px] rounded-full bg-black/85 border border-gold/30 group-hover:bg-black/70 transition-colors duration-200" />
            </button>
          </div>
        )}

        {/* PROCESSING OVERLAY — progress + countdown */}
        {phase === "processing" && (
          <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-50 w-[min(88vw,420px)]">
            <div className="rounded-3xl border border-white/10 bg-black/60 backdrop-blur-2xl px-6 py-5">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <Loader2 size={14} className="text-gold animate-spin" />
                  <span className="text-[11px] font-mono tracking-widest text-gold/80">{stageLabel.toUpperCase()}</span>
                </div>
                <span className="text-xs font-mono text-white/60">{progress}%</span>
              </div>

              <div className="w-full h-1.5 rounded-full bg-white/10 overflow-hidden mb-4">
                <motion.div
                  animate={{ width: `${progress}%` }}
                  transition={{ ease: "linear", duration: 0.15 }}
                  className="h-full rounded-full bg-gradient-to-r from-gold-dark to-gold"
                />
              </div>

              {/* Big synchronized countdown */}
              <div className="flex items-center justify-center gap-2 mb-1">
                <span className="text-5xl font-bold text-white font-poppins tabular-nums">{secondsLeft}</span>
                <span className="text-xs text-white/50 font-mono tracking-widest">SECONDS</span>
              </div>
              <p className="text-center text-[11px] text-white/40">ESTIMATED TIME REMAINING</p>

              {cancelable && (
                <button
                  onClick={cancelAnalysis}
                  aria-label="Cancel scene analysis"
                  className="mt-4 w-full flex items-center justify-center gap-2 py-2 rounded-xl text-xs font-semibold text-white/80 border border-white/15 bg-white/5 hover:bg-white/10 transition-colors"
                >
                  <X size={14} /> Cancel Analysis
                </button>
              )}
            </div>
          </div>
        )}

        {/* ERROR STATE */}
        {phase === "error" && (
          <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-50 w-[min(88vw,360px)]">
            <div className="rounded-3xl border border-red-400/20 bg-black/70 backdrop-blur-2xl px-6 py-5 text-center">
              <AlertTriangle size={26} className="text-red-400 mx-auto mb-2" />
              <h3 className="text-white font-semibold mb-1">{errorMsg}</h3>
              <p className="text-white/50 text-xs mb-4">The frozen frame is kept so you can retry.</p>
              <button
                onClick={() => {
                  // Retry with the retained frozen image.
                  busyRef.current = false
                  startedAtRef.current = Date.now()
                  setErrorMsg("")
                  setProgress(0)
                  setStageLabel(STAGES[0].label)
                  setCancelable(false)
                  setPhase("processing")
                  setShowPanel(false)
                  announce("Retrying scene analysis.", { priority: 1 })
                  const retryUrl = frozen || sessionMemory.lastResult?.capture
                  if (retryUrl) {
                    dataUrlToBlob(retryUrl).then((blob) =>
                      runAnalysis(blob, retryUrl)
                    )
                  } else {
                    setPhase("capture")
                  }
                }}
                aria-label="Retry scene capture"
                className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-xs font-semibold text-black bg-gradient-to-r from-gold-dark to-gold hover:brightness-110 transition-all"
              >
                <RefreshCw size={14} /> Retry Capture
              </button>
            </div>
          </div>
        )}

        {/* CAPTURE AGAIN (after success) */}
        {phase === "completed" && (
          <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-50">
            <button
              onClick={captureAgain}
              aria-label="Capture new frame"
              className="flex items-center gap-2 px-6 py-3 rounded-full text-sm font-semibold text-black bg-gradient-to-r from-gold-dark to-gold hover:brightness-110 hover:-translate-y-0.5 active:scale-95 transition-all duration-200 shadow-[0_8px_28px_rgba(255,179,71,0.35)]"
            >
              <Camera size={16} /> Capture Again
            </button>
          </div>
        )}

        {/* DESCRIPTION PANEL — visible only after response */}
        <AnimatePresence>
          {phase === "completed" && showPanel && result && (
            <motion.div
              initial={{ x: 360, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 360, opacity: 0 }}
              transition={{ type: "tween", duration: 0.3 }}
              className="absolute top-0 right-0 h-full w-[min(360px,100vw)] z-50 bg-black/60 backdrop-blur-2xl border-l border-gold/15 p-6 overflow-y-auto"
            >
              <div className="flex items-center gap-2 mb-6">
                  <ScanEye size={18} className="text-gold" />
                  <span className="text-[10px] font-mono tracking-widest text-gold/70">SMART DESCRIPTION</span>
                </div>

              <p className="text-white/90 leading-relaxed text-[15px] mb-6">{result.description}</p>

              {/* OBJECTS */}
              <h4 className="text-[10px] font-mono tracking-widest text-white/40 mb-3">TRACKED OBJECTS</h4>
              <div className="space-y-3 mb-6">
                {objects.length === 0 && (
                  <p className="text-white/30 text-xs">No recognisable objects in this frame.</p>
                )}
                {objects.map((o, i) => (
                  <div key={o.label + i} className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-sm capitalize text-white/90">{o.label}</span>
                      <span className="text-[10px] font-mono text-gold">{Math.round(o.confidence * 100)}% CONFIDENCE</span>
                    </div>
                    <div className="w-full h-1 rounded-full bg-white/10 overflow-hidden">
                      <motion.div
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.round(o.confidence * 100)}%` }}
                        transition={{ duration: 0.6 }}
                        className="h-full bg-gradient-to-r from-gold-dark to-gold"
                      />
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between gap-3 mt-auto">
                <button
                  onClick={() => speak(result.speech_text)}
                  aria-label="Replay scene description"
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold text-black bg-gradient-to-r from-gold-dark to-gold hover:brightness-110 transition-all"
                >
                  <Volume2 size={14} /> Replay Description
                </button>
                <button
                  onClick={captureAgain}
                  aria-label="Capture new frame"
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold text-white/80 border border-white/10 bg-white/5 hover:bg-white/10 transition-colors"
                >
                  <Camera size={14} /> New Capture
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* FLOATING "VIEW DESCRIPTION" pill when panel is closed */}
        {phase === "completed" && result && !showPanel && (
          <motion.button
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            onClick={() => {
              setShowPanel(true)
              announce("Description panel opened.", { priority: 1 })
            }}
            aria-label="View scene description"
            className="absolute top-24 right-6 z-40 flex items-center gap-2 px-4 py-2.5 rounded-full border border-gold/20 bg-black/60 backdrop-blur-xl text-white/80 hover:text-gold hover:border-gold/40 transition-colors cursor-pointer"
          >
            <CheckCircle2 size={15} className="text-gold" />
            <span className="text-xs font-mono">VIEW DESCRIPTION</span>
          </motion.button>
        )}
      </div>
    </HUDOverlay>
  )
}