import { useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import {
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  ScanSearch,
  Search,
  Sparkles,
  Target,
} from "lucide-react"
import HUDOverlay from "../components/HUDOverlay"
import { CameraView } from "../components/CameraView"
import { useVision } from "../hooks/useVision"
import { useTTS } from "../context/TTSContext"
import TTSButton from "../components/TTSButton"

const COCO_SUGGESTIONS = [
  "person", "bicycle", "car", "motorcycle", "bus", "truck",
  "traffic light", "chair", "couch", "dining table", "backpack",
  "bottle", "cup", "bowl", "book", "laptop", "cell phone", "keyboard",
]

const SEARCH_SUGGESTIONS = COCO_SUGGESTIONS.slice(0, 8)

export default function SearchFeature() {
  const { announce } = useTTS()
  const [target, setTarget] = useState("")
  const [started, setStarted] = useState(false)
  const [status, setStatus] = useState("scanning")
  const [statusBanner, setStatusBanner] = useState(true)
  const hadMatchRef = useRef(false)
  const lastSentRef = useRef({ term: "", at: 0 })
  const bannerTimerRef = useRef(null)

  const { connected, detections, lastMessage, lastMessageMeta, sendSearch, uiConfig, frameDims } =
    useVision({ mode: started ? "object" : "camera" })

  // Leaving the page must clear the backend search target. Otherwise the
  // relaxed search threshold persists server-side and produces phantom
  // "person ahead" announcements on the next page/connection.
  useEffect(() => () => sendSearch(""), [sendSearch])

  const term = target.trim().toLowerCase()

  const matching = started && term
    ? detections.filter((d) =>
        d.class_name.toLowerCase().includes(term)
      )
    : []

  const bestConfidence = matching.length
    ? Math.max(...matching.map((d) => Number(d.confidence) || 0)) * 100
    : null

  // Smooth transitions: found -> lost -> searching/Found, never flash.
  useEffect(() => {
    if (!started) {
      setStatus("scanning")
      return
    }
    if (matching.length > 0) {
      hadMatchRef.current = true
      setStatus("found")
      announce(`${target.trim()} found.`, { priority: 2 })
    } else if (hadMatchRef.current) {
      setStatus("lost")
      announce(`${target.trim()} lost.`, { priority: 1 })
    } else {
      setStatus("searching")
    }
  }, [started, matching])

  // Transient base-of-page status line: auto-hides after 3 seconds,
  // re-appears after every search / status change.
  useEffect(() => {
    setStatusBanner(true)
    if (bannerTimerRef.current) clearTimeout(bannerTimerRef.current)
    bannerTimerRef.current = setTimeout(() => setStatusBanner(false), 3000)
    return () => clearTimeout(bannerTimerRef.current)
  }, [status])

  const runSearch = (value) => {
    const t = (value || "").trim().toLowerCase()
    if (!t) return
    const now = Date.now()
    if (lastSentRef.current.term === t && now - lastSentRef.current.at < 2500) {
      return
    }
    lastSentRef.current = { term: t, at: now }
    hadMatchRef.current = false
    setTarget(value)
    setStatus("searching")
    setStarted(true)
    sendSearch(t)
    announce(`Searching for ${t}.`, { priority: 1 })
  }

  const startSearch = (e) => {
    e.preventDefault()
    runSearch(target)
  }

  // Back: reset to the initial detection screen in place. Camera keeps
  // running, all quick options reappear, and the backend search target is
  // cleared (empty search = normal confidence + no more "found" speech).
  const resetSearch = () => {
    hadMatchRef.current = false
    lastSentRef.current = { term: "", at: 0 }
    setTarget("")
    setStarted(false)
    setStatus("scanning")
    sendSearch("")
  }

  const statusMeta = {
    scanning: {
      icon: ScanSearch,
      label: "Detection Engine Active",
      dot: "bg-green-500",
      iconColor: "text-green-500",
    },
    searching: {
      icon: Search,
      label: `Searching for "${target.trim()}"`,
      dot: "bg-amber-500",
      iconColor: "text-amber-500",
    },
    found: {
      icon: CheckCircle2,
      label: `${target.trim()} Found`,
      dot: "bg-emerald-500",
      iconColor: "text-emerald-500",
    },
    lost: {
      icon: AlertTriangle,
      label: "Lost Target — Continuing Scan…",
      dot: "bg-amber-500",
      iconColor: "text-orange-500",
    },
  }[status]

  const StatusIcon = statusMeta.icon

  return (
    <HUDOverlay title="SMART SEARCH — OBJECT DETECTION">
      <div className="relative w-full h-screen overflow-hidden bg-black">
        <CameraView detections={started ? matching : []} active={true} ui={uiConfig} frame={frameDims} />

        {/* BACK — floating glass pill, same style as the other modes */}
        <Link
          to="/home"
          className="absolute top-20 left-6 z-50 flex items-center gap-2 px-4 py-2.5 rounded-full bg-white/30 backdrop-blur-2xl border border-black/10 shadow-[0_8px_24px_rgba(0,0,0,0.15)] text-black hover:bg-white/60 hover:border-amber-500/40 hover:text-amber-600 hover:-translate-y-0.5 transition-all duration-200 cursor-pointer"
        >
          <ArrowLeft size={18} />
          <span className="text-sm font-medium">Back</span>
        </Link>

        {/* TTS Toggle */}
        <div className="absolute top-20 right-6 z-50">
          <TTSButton />
        </div>

        {/* SEARCH BAR — glass, raised, wider, Back on the left */}
        <form
          onSubmit={startSearch}
          className="absolute top-16 left-1/2 -translate-x-1/2 z-40 w-[min(94vw,640px)]"
        >
          <div className="flex items-center gap-3 px-4 py-2.5 rounded-2xl bg-white/30 backdrop-blur-2xl border border-black/10 shadow-[0_12px_40px_rgba(0,0,0,0.25)] focus-within:ring-2 focus-within:ring-amber-400/60 focus-within:border-amber-400/40 transition-all duration-200">
            <button
              type="button"
              onClick={resetSearch}
              aria-label="Back to live detection"
              className="flex items-center justify-center w-9 h-9 shrink-0 rounded-xl bg-white/40 border border-black/10 text-black hover:text-amber-600 hover:bg-white/70 hover:border-amber-500/40 hover:-translate-y-0.5 active:scale-95 transition-all duration-200 cursor-pointer"
            >
              <ArrowLeft size={18} />
            </button>

            <Search size={18} className="text-amber-500 shrink-0" />
            <input
              type="text"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder="What are you looking for? e.g. water bottle"
              className="flex-1 bg-transparent text-[15px] text-black placeholder-gray-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={!target.trim()}
              aria-label={started ? "Search again" : "Find object"}
              className="px-5 py-2 rounded-xl text-xs font-semibold text-black bg-gradient-to-r from-amber-500 to-yellow-400 hover:brightness-105 hover:shadow-[0_8px_28px_rgba(245,158,11,0.45)] hover:-translate-y-0.5 active:scale-95 transition-all duration-200 disabled:opacity-40 disabled:shadow-none disabled:hover:translate-y-0 disabled:cursor-not-allowed"
            >
              {started ? "Search Again" : "Find"}
            </button>
          </div>

          {/* SUGGESTION CHIPS — always visible, glass pills, amber hover */}
          <div className="mt-3 flex flex-wrap justify-center gap-2">
            {SEARCH_SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => runSearch(s)}
                aria-label={`Search for ${s}`}
                className="px-3.5 py-1.5 text-xs text-black bg-white/30 border border-black/10 rounded-full backdrop-blur-xl shadow-sm hover:bg-white/60 hover:text-amber-600 hover:border-amber-500/40 hover:-translate-y-0.5 transition-all duration-200 cursor-pointer"
              >
                {s}
              </button>
            ))}
          </div>
        </form>

        {/* STATUS LINE — transient glass pill at the base of the page */}
        <AnimatePresence>
          {statusBanner && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 20 }}
              transition={{ duration: 0.25 }}
              className="absolute bottom-16 left-1/2 -translate-x-1/2 z-40"
            >
              <div className="flex items-center gap-2.5 px-4 py-2 rounded-full bg-white/30 backdrop-blur-2xl border border-black/10 shadow-[0_8px_24px_rgba(0,0,0,0.15)]">
                <span className={`w-2 h-2 rounded-full ${statusMeta.dot} animate-pulse`} />
                <StatusIcon size={15} className={`${statusMeta.iconColor}`} />
                <span className="text-xs font-medium tracking-wide text-black">
                  {statusMeta.label}
                </span>
                {status === "found" && (
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-white/40 border border-black/10 text-black">
                    {matching.length} · {bestConfidence != null ? `${bestConfidence.toFixed(0)}%` : "—"}
                  </span>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* MATCH COUNTER — glass card */}
        {started && status === "found" && matching.length > 0 && (
          <div className="absolute bottom-6 right-6 z-40 px-4 py-2.5 rounded-2xl bg-white/30 backdrop-blur-2xl border border-black/10 shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
            <div className="flex items-center gap-2">
              <Target size={16} className="text-amber-500" />
              <span className="text-xs font-semibold text-black">
                {matching.length} MATCH{matching.length === 1 ? "" : "ES"}
              </span>
            </div>
          </div>
        )}

        {/* STATUS MESSAGE — notification card */}
        {started && lastMessage && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 20 }}
            className="absolute bottom-24 left-1/2 -translate-x-1/2 z-40 px-6 py-4 rounded-2xl bg-white/30 backdrop-blur-2xl border border-black/10 shadow-[0_8px_32px_rgba(0,0,0,0.2)] text-center"
          >
            <div className="flex items-center justify-center gap-2 mb-1">
              <Sparkles size={14} className="text-amber-500" />
              <span className="text-[10px] font-semibold tracking-widest text-gray-500">
                {lastMessageMeta.category === "search" ? "SEARCH RESULT" : "SMART STATUS"}
              </span>
            </div>
            <p className="text-sm text-black">{lastMessage}</p>
          </motion.div>
        )}

        {/* LINKING INDICATOR — floating glass pill */}
        {!connected && (
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-40 flex items-center gap-2 px-4 py-2 rounded-full bg-white/30 backdrop-blur-2xl border border-black/10 shadow-[0_8px_24px_rgba(0,0,0,0.15)]">
            <RefreshCw size={13} className="text-amber-500 animate-spin" />
            <span className="text-xs font-medium text-black">LINKING DETECTION ENGINE…</span>
          </div>
        )}
      </div>
    </HUDOverlay>
  )
}
