import { useEffect } from "react"
import { Link } from "react-router-dom"
import { motion } from "framer-motion"
import { TriangleAlert, ShieldAlert, ArrowLeft } from "lucide-react"
import HUDOverlay from "../components/HUDOverlay"
import { CameraView } from "../components/CameraView"
import { useVision } from "../hooks/useVision"
import { useTTS } from "../context/TTSContext"
import TTSButton from "../components/TTSButton"

export default function ThreatFeature() {
  const { announce } = useTTS()
  const { connected, detections, lastMessage, uiConfig, frameDims } = useVision({ mode: "text" })

  const highThreats = detections.filter((d) => (d.threat_level || 0) >= 2)

  useEffect(() => {
    announce("Threat detection mode active.", { priority: 1 })
  }, [])

  useEffect(() => {
    if (highThreats.length > 0) {
      const names = highThreats.map((t) => t.class_name).join(", ")
      announce(`Warning. High threat detected: ${names}.`, { priority: 0 })
    }
  }, [highThreats.length])

  return (
    <HUDOverlay title="THREAT DETECTION — HAZARD ANALYSIS">
      <div className="relative w-full h-screen overflow-hidden bg-black">
        <CameraView detections={detections} active={true} ui={uiConfig} frame={frameDims} />

        <Link
          to="/home"
          aria-label="Back to home"
          className="absolute top-20 left-6 z-50 flex items-center gap-2 px-5 py-3 rounded-full border border-gold/20 bg-black/60 backdrop-blur-xl text-white/70 hover:text-gold transition-all cursor-pointer"
        >
          <ArrowLeft size={18} />
          <span className="text-sm font-medium">Back</span>
        </Link>

        {/* TTS Toggle */}
        <div className="absolute top-20 right-6 z-50">
          <TTSButton />
        </div>
        <div className="absolute top-28 right-6 z-40 flex items-center gap-2 px-4 py-2 rounded-full border border-white/10 bg-black/40 backdrop-blur-xl">
          <span className={`w-2 h-2 rounded-full ${connected ? "bg-green-400 animate-pulse" : "bg-yellow-400"}`} />
          <span className="text-xs font-mono text-white/70">THREAT MODE ACTIVE</span>
        </div>

        {/* THREAT LEVEL */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          className="absolute top-1/2 left-8 -translate-y-1/2 z-40"
        >
          <div className="flex flex-col items-center gap-3 px-6 py-8 rounded-3xl border border-red-400/20 bg-black/60 backdrop-blur-2xl">
            <ShieldAlert
              size={32}
              className={highThreats.length > 0 ? "text-red-400 animate-pulse" : "text-green-400"}
            />
            <div className="text-center">
              <div className={`text-4xl font-bold font-poppins ${highThreats.length > 0 ? "text-red-400" : "text-green-400"}`}>
                {highThreats.length}
              </div>
              <div className="text-[10px] tracking-widest text-white/40 font-mono mt-1">
                HIGH THREATS
              </div>
            </div>
            {highThreats.length > 0 ? (
              <div className="space-y-1.5 mt-2">
                {highThreats.slice(0, 4).map((t) => (
                  <div
                    key={t.id}
                    className="flex items-center gap-2 px-3 py-1 rounded-full border border-red-400/30 bg-red-400/10"
                  >
                    <TriangleAlert size={12} className="text-red-400" />
                    <span className="text-xs text-red-300">{t.class_name}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs font-mono text-green-400">ALL CLEAR</div>
            )}
          </div>
        </motion.div>

        {/* LAST AUDIO ALERT */}
        {lastMessage && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="absolute bottom-24 left-1/2 -translate-x-1/2 z-40 px-6 py-4 rounded-2xl border border-red-400/10 bg-black/60 backdrop-blur-2xl text-center"
          >
            <div className="flex items-center justify-center gap-2 mb-1">
              <TriangleAlert size={14} className="text-red-400" />
              <span className="text-[10px] font-mono tracking-widest text-red-400/60">
                SMART VOICE ALERT
              </span>
            </div>
            <p className="text-sm text-white/90">{lastMessage}</p>
          </motion.div>
        )}
      </div>
    </HUDOverlay>
  )
}
