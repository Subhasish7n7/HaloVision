import { useEffect, useState, useRef } from "react"
import { Link } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"

import {
  ArrowLeft,
  Navigation,
  MapPin,
  Volume2,
  ShieldAlert,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react"

import HUDOverlay from "../components/HUDOverlay"
import { CameraView } from "../components/CameraView"
import { DetectionPanel } from "../components/DetectionPanel"
import { useVision } from "../hooks/useVision"
import { useTTS } from "../context/TTSContext"
import TTSButton from "../components/TTSButton"

export default function NavigationFeature() {
  const { announce } = useTTS()
  const [showGuide, setShowGuide] = useState(true)
  const [showPanel, setShowPanel] = useState(false)
  const { connected, detections, uiConfig, perf, frameDims, pathStatus } = useVision({ mode: "camera" })

  useEffect(() => {
    const timer = setTimeout(() => setShowGuide(false), 4000)
    announce("Navigation mode active. Smart guidance system is running.", { priority: 1 })
    return () => clearTimeout(timer)
  }, [])

  const maxThreat = detections.reduce(
    (max, d) => Math.max(max, d.threat_level || 0),
    0
  )

  let threatColor = "text-cyan-400"
  let threatText = "SAFE"

  if (maxThreat >= 3) {
    threatColor = "text-red-400"
    threatText = "HIGH ALERT"
  } else if (maxThreat === 2) {
    threatColor = "text-yellow-400"
    threatText = "CAUTION"
  }

  return (
    <HUDOverlay title="NAVIGATION MODE — SMART PATHFINDING">

      <div className="relative w-full h-screen overflow-hidden bg-black">

        {/* FULLSCREEN CAMERA */}
        <CameraView
          detections={detections}
          active={true}
          ui={uiConfig}
          frame={frameDims}
        />

        {/* BACK BUTTON */}
        <Link
          to="/home"
          aria-label="Back to home"
          className="
            absolute top-20 left-6 z-50
            flex items-center gap-2
            px-5 py-3
            rounded-full
            border border-gold/20
            bg-black/60 backdrop-blur-xl
            text-white/70 hover:text-gold
            transition-all
            cursor-pointer
          "
        >
          <ArrowLeft size={18} />
          <span className="text-sm font-medium">Back</span>
        </Link>

        {/* TTS Toggle */}
        <div className="absolute top-20 right-6 z-50">
          <TTSButton />
        </div>
        <div className={`absolute top-28 z-40 flex items-center gap-3 transition-all duration-300 ${showPanel ? "right-[360px]" : "right-6"}`}>

          <div className={`
            flex items-center gap-2
            px-4 py-2
            rounded-full
            border
            backdrop-blur-xl
            transition-all duration-300
            ${connected ? "border-green-400/20 bg-black/40" : "border-amber-400/20 bg-black/50"}
          `}>
            <span className={`w-2 h-2 rounded-full animate-pulse ${connected ? "bg-green-400" : "bg-amber-400"}`} />

            <span className={`text-xs font-mono ${connected ? "text-green-400" : "text-amber-400"}`}>
              {connected ? "SMART ACTIVE" : "LINKING…"}
            </span>
          </div>

          {perf && (
            <div className="
              flex items-center gap-2
              px-4 py-2
              rounded-full
              border border-white/10
              bg-black/40 backdrop-blur-xl
            ">
              <span className="text-[10px] font-mono text-cyan-300">
                {perf.fps ? `${perf.fps.toFixed(1)} FPS` : "…"}
              </span>
              <span className="w-px h-3 bg-white/15" />
              <span className="text-[10px] font-mono text-white/50">
                INF {perf.infer_ms ? `${perf.infer_ms.toFixed(0)}ms` : "…"}
                {perf.depth_ms ? ` · DPT ${perf.depth_ms.toFixed(0)}ms` : ""}
              </span>
            </div>
          )}

          <div className="
            flex items-center gap-2
            px-4 py-2
            rounded-full
            border border-white/10
            bg-black/40 backdrop-blur-xl
          ">
            <ShieldAlert
              size={16}
              className={threatColor}
            />

            <span className={`text-xs font-mono ${threatColor}`}>
              {threatText}
            </span>
          </div>

          {/* PATH STATUS — shown after hand gesture triggers analysis */}
          <AnimatePresence>
            {pathStatus && (
              <motion.div
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ duration: 0.3 }}
                className={`
                  flex items-center gap-2
                  px-4 py-2
                  rounded-full
                  border backdrop-blur-xl
                  ${pathStatus.status === "CLEAR"
                    ? "border-green-400/30 bg-green-400/10"
                    : pathStatus.status === "BLOCKED"
                    ? "border-red-400/30 bg-red-400/10"
                    : "border-amber-400/30 bg-amber-400/10"
                  }
                `}
              >
                <span className={`
                  w-2 h-2 rounded-full
                  ${pathStatus.status === "CLEAR"
                    ? "bg-green-400"
                    : pathStatus.status === "BLOCKED"
                    ? "bg-red-400"
                    : "bg-amber-400"
                  }
                `} />
                <span className={`
                  text-xs font-mono
                  ${pathStatus.status === "CLEAR"
                    ? "text-green-400"
                    : pathStatus.status === "BLOCKED"
                    ? "text-red-400"
                    : "text-amber-400"
                  }
                `}>
                  {pathStatus.status === "CLEAR"
                    ? "PATH CLEAR"
                    : pathStatus.status === "BLOCKED"
                    ? "PATH BLOCKED"
                    : "PATH UNCERTAIN"
                  }
                </span>
              </motion.div>
            )}
          </AnimatePresence>

        </div>

        {/* CENTER HUD - auto-hides after 4s */}
        <AnimatePresence>
          {showGuide && (
            <div className="
              absolute bottom-8 left-1/2
              -translate-x-1/2
              z-40
            ">
              <motion.div
                initial={{ opacity: 0, y: 30 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 20 }}
                transition={{ duration: 0.5 }}
                className="
                  px-8 py-5
                  rounded-3xl
                  border border-gold/10
                  bg-black/50 backdrop-blur-2xl
                  min-w-[340px]
                  text-center
                "
              >
                <div className="
                  flex items-center justify-center
                  gap-2 mb-3
                ">
                  <Navigation
                    size={18}
                    className="text-gold"
                  />

                  <span className="
                    text-xs font-mono tracking-[0.2em]
                    text-gold/70
                  ">
                    LIVE NAVIGATION
                  </span>
                </div>

                <h2 className="
                  text-3xl font-bold text-white
                  mb-2
                ">
                  Continue Forward
                </h2>

                <p className="text-white/50 text-sm">
                  smart guidance system active
                </p>
              </motion.div>
            </div>
          )}
        </AnimatePresence>

        {/* HUD CORNERS */}
        <div className="absolute top-0 left-0 w-20 h-20 border-l-2 border-t-2 border-gold/30 z-30" />
        <div className={`absolute top-0 w-20 h-20 border-r-2 border-t-2 border-gold/30 z-30 transition-all duration-300 ${showPanel ? "right-[340px]" : "right-0"}`} />
        <div className="absolute bottom-0 left-0 w-20 h-20 border-l-2 border-b-2 border-gold/30 z-30" />
        <div className={`absolute bottom-0 w-20 h-20 border-r-2 border-b-2 border-gold/30 z-30 transition-all duration-300 ${showPanel ? "right-[340px]" : "right-0"}`} />

        {/* TOGGLE BUTTON - always visible */}
        <button
          onClick={() => setShowPanel(!showPanel)}
          aria-label={showPanel ? "Close detection panel" : "Open detection panel"}
          className="absolute top-1/2 right-0 -translate-y-1/2 z-50 px-2 py-6 rounded-l-full border border-gold/20 bg-black/60 backdrop-blur-xl text-white/50 hover:text-gold hover:border-gold/40 transition-all"
        >
          {showPanel ? <PanelRightOpen size={18} /> : <PanelRightClose size={18} />}
        </button>

        {/* RIGHT PANEL - toggleable */}
        <AnimatePresence>
          {showPanel && (
            <motion.div
              initial={{ x: 340 }}
              animate={{ x: 0 }}
              exit={{ x: 340 }}
              transition={{ type: "tween", duration: 0.25 }}
              className="
                absolute top-0 right-0
                h-screen w-[340px]
                z-40
                bg-black/60
                backdrop-blur-2xl
                border-l border-gold/10
                p-6 overflow-y-auto
              "
            >

              <div className="mb-8">

                <h2 className="text-white text-xl font-semibold mb-2">
                  Navigation Intelligence
                </h2>

                <p className="text-white/40 text-sm">
                  Realtime smart environment analysis
                </p>

              </div>

              {/* STATUS CARDS */}
              <div className="space-y-4 mb-8">

                {[
                  {
                    icon: MapPin,
                    label: "GPS STATUS",
                    value: connected
                      ? "CONNECTED"
                      : "CONNECTING",
                    color: connected
                      ? "text-green-400"
                      : "text-yellow-400",
                  },

                  {
                    icon: Volume2,
                    label: "VOICE GUIDE",
                    value: "ACTIVE",
                    color: "text-gold",
                  },

                  {
                    icon: Navigation,
                    label: "OBJECTS",
                    value: `${detections.length}`,
                    color: "text-cyan-400",
                  },

                ].map((item) => (

                  <div
                    key={item.label}
                    className="
                      p-4 rounded-2xl
                      border border-white/5
                      bg-white/[0.02]
                    "
                  >

                    <div className="flex items-center gap-3">

                      <item.icon
                        size={18}
                        className="text-gold/70"
                      />

                      <div>

                        <div className="
                          text-[10px]
                          tracking-widest
                          text-white/30
                          font-mono
                        ">
                          {item.label}
                        </div>

                        <div className={`text-sm font-medium ${item.color}`}>
                          {item.value}
                        </div>

                      </div>

                    </div>

                  </div>

                ))}

              </div>

              {/* LIVE DETECTIONS */}
              <DetectionPanel detections={detections} ui={uiConfig} />

            </motion.div>
          )}
        </AnimatePresence>

      </div>

    </HUDOverlay>
  )
}
