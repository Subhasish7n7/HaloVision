import { motion, AnimatePresence } from "framer-motion"

import {
  ShieldAlert,
  ScanSearch,
  Eye,
  AlertTriangle,
  Radar,
} from "lucide-react"

export const DetectionPanel = ({
  detections,
  ui = null,
}) => {
  const uiConfig = ui || {}
  const showTrackId = uiConfig.show_tracking_ids !== false
  const showConfidence = uiConfig.show_confidence !== false
  const getStyles = (className) => {
    const lower = (className || "").toLowerCase()

    if (
      lower.includes("person") ||
      lower.includes("human")
    ) {
      return {
        border: "border-red-400/30",
        bg: "bg-red-400/10",
        text: "text-red-400",
        icon: AlertTriangle,
        glow: "shadow-[0_0_25px_rgba(248,113,113,0.2)]",
      }
    }

    if (
      lower.includes("car") ||
      lower.includes("vehicle") ||
      lower.includes("truck") ||
      lower.includes("bus") ||
      lower.includes("motorcycle")
    ) {
      return {
        border: "border-yellow-400/30",
        bg: "bg-yellow-400/10",
        text: "text-yellow-400",
        icon: Radar,
        glow: "shadow-[0_0_25px_rgba(250,204,21,0.15)]",
      }
    }

    return {
      border: "border-cyan-400/30",
      bg: "bg-cyan-400/10",
      text: "text-cyan-400",
      icon: Eye,
      glow: "shadow-[0_0_25px_rgba(34,211,238,0.15)]",
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* HEADER */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <ShieldAlert
            size={20}
            className="text-gold"
          />

          <h2 className="text-white text-lg font-semibold">
            Detection Panel
          </h2>
        </div>

        <p className="text-white/40 text-sm">
          Realtime smart environment analysis
        </p>
      </div>

      {/* STATS */}
      <div
        className="
          mb-6
          p-4 rounded-2xl
          border border-gold/10
          bg-gold/5
          backdrop-blur-xl
        "
      >
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[10px] tracking-widest text-gold/50 font-mono">
              ACTIVE DETECTIONS
            </div>

            <div className="text-3xl font-bold text-white mt-1">
              {detections.length}
            </div>
          </div>

          <div
            className="
              w-14 h-14 rounded-2xl
              flex items-center justify-center
              bg-gold/10 border border-gold/20
            "
          >
            <ScanSearch
              size={24}
              className="text-gold"
            />
          </div>
        </div>
      </div>

      {/* DETECTIONS */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        <AnimatePresence>
          {detections.length === 0 && (
            <motion.div
              initial={{
                opacity: 0,
                y: 10,
              }}

              animate={{
                opacity: 1,
                y: 0,
              }}

              className="
                rounded-2xl
                border border-white/5
                bg-white/[0.02]
                p-6
                text-center
              "
            >
              <div
                className="
                  w-14 h-14 mx-auto mb-4
                  rounded-full
                  bg-white/5
                  flex items-center justify-center
                "
              >
                <Eye
                  size={24}
                  className="text-white/20"
                />
              </div>

              <h3 className="text-white/60 font-medium mb-1">
                No Detections
              </h3>

              <p className="text-white/30 text-sm">
                smart scanning environment...
              </p>
            </motion.div>
          )}

          {detections.map((d, i) => {
            const className = d.class_name || d.label || "unknown"
            const styles = getStyles(className)

            const Icon = styles.icon

            return (
              <motion.div
                key={d.id || i}

                initial={{
                  opacity: 0,
                  x: 20,
                }}

                animate={{
                  opacity: 1,
                  x: 0,
                }}

                exit={{
                  opacity: 0,
                  x: -20,
                }}

                transition={{
                  delay: i * 0.05,
                }}

                className={`
                  relative overflow-hidden
                  rounded-2xl border
                  ${styles.border}
                  ${styles.bg}
                  ${styles.glow}
                  backdrop-blur-xl
                  p-4
                `}
              >
                {/* GLOW */}
                <div
                  className="
                    absolute inset-0 opacity-20
                    pointer-events-none
                  "
                  style={{
                    background:
                      "radial-gradient(circle at top right, rgba(255,255,255,0.15), transparent 60%)",
                  }}
                />

                <div className="relative z-10">
                  {/* TOP */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div
                        className={`
                          w-11 h-11 rounded-xl
                          flex items-center justify-center
                          ${styles.bg}
                          border ${styles.border}
                        `}
                      >
                        <Icon
                          size={20}
                          className={styles.text}
                        />
                      </div>

                      <div>
                        <h3
                          className={`
                            text-sm font-semibold
                            ${styles.text}
                          `}
                        >
                          {className}
                        </h3>

                        <p className="text-[11px] text-white/40 flex items-center gap-2">
                          {showTrackId && d.track_id != null && (
                            <span className="text-white/70 font-mono">
                              ID: {d.track_id}
                            </span>
                          )}
                          {showTrackId && d.track_id != null && (
                            <span className="opacity-40">•</span>
                          )}
                          Smart Recognized Object
                        </p>
                      </div>
                    </div>

                    {/* LIVE DOT */}
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />

                      <span className="text-[10px] text-green-400 font-mono">
                        LIVE
                      </span>
                    </div>
                  </div>

                  {/* CONFIDENCE */}
                  {showConfidence && (
                    <div className="mb-2">
                      <div className="flex items-center justify-between text-[10px] text-white/40 mb-1">
                        <span>CONFIDENCE</span>

                        <span>
                          {Number.isFinite(d.confidence)
                            ? `${Math.round(
                                d.confidence * 100
                              )}%`
                            : "—"}
                        </span>
                      </div>

                      <div className="w-full h-1 rounded-full bg-white/10 overflow-hidden">
                        <motion.div
                          initial={{
                            width: 0,
                          }}

                          animate={{
                            width: `${
                              Number.isFinite(d.confidence)
                                ? d.confidence * 100
                                : 0
                            }%`,
                          }}

                          transition={{
                            duration: 0.6,
                          }}

                          className={`
                            h-full rounded-full
                            ${styles.bg}
                          `}
                        />
                      </div>
                    </div>
                  )}

                  {/* BBOX */}
                  {d.bbox && (
                    <div className="mt-3 text-[10px] text-white/30 font-mono">
                      X:{d.bbox[0]} Y:{d.bbox[1]}
                    </div>
                  )}
                </div>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </div>
  )
}
