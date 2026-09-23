import { Volume2, VolumeX } from "lucide-react"
import { useTTS } from "../context/TTSContext"

export default function TTSButton({ className = "" }) {
  const { enabled, toggle } = useTTS()

  return (
    <button
      onClick={toggle}
      aria-pressed={enabled}
      aria-label={enabled ? "Turn text to speech off" : "Turn text to speech on"}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11px] font-mono tracking-wider border transition-all duration-200 cursor-pointer ${
        enabled
          ? "border-gold/30 bg-gold/10 text-gold hover:bg-gold/20"
          : "border-white/10 bg-white/5 text-white/40 hover:text-white/60 hover:border-white/20"
      } ${className}`}
    >
      {enabled ? <Volume2 size={12} className="shrink-0" /> : <VolumeX size={12} className="shrink-0" />}
      <span>TTS {enabled ? "ON" : "OFF"}</span>
    </button>
  )
}
