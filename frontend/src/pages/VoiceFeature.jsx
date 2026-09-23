import { useState, useEffect, useRef } from "react"
import { Link } from "react-router-dom"
import { motion, AnimatePresence } from "framer-motion"
import { Mic, MicOff, Volume2, Sparkles, ArrowLeft, ChevronRight } from "lucide-react"
import FeatureLayout from "../components/FeatureLayout"
import GlassCard from "../components/GlassCard"
import { useVision } from "../hooks/useVision"
import { useTTS } from "../context/TTSContext"
import TTSButton from "../components/TTSButton"

const commands = [
  "Find water bottle",
  "Describe the scene",
  "What's in front of me?",
  "Threat mode",
  "Navigate mode",
  "Mute",
  "Unmute",
]

export default function VoiceFeature() {
  const { announce, enabled: ttsEnabled, setEnabled: setTTSEnabled } = useTTS()
  const [listening, setListening] = useState(false)
  const [transcript, setTranscript] = useState("")
  const [history, setHistory] = useState([])
  const [dots, setDots] = useState("")
  const [supportError, setSupportError] = useState("")
  const recognitionRef = useRef(null)

  const { connected, lastMessage, lastMessageMeta, sendVoice } =
    useVision({ mode: "voice" })

  useEffect(() => {
    if (!listening) return
    const interval = setInterval(() => {
      setDots((d) => (d.length >= 3 ? "" : d + "."))
    }, 500)
    return () => clearInterval(interval)
  }, [listening])

  // Surface the latest assistant reply
  useEffect(() => {
    if (lastMessage) {
      setHistory((h) => {
        const next = [...h, { role: "ai", text: lastMessage }]
        return next.slice(-20)
      })
      announce(lastMessage, { priority: 2 })
    }
  }, [lastMessage, announce])

  const stopListening = () => {
    setListening(false)
    try {
      recognitionRef.current?.stop()
    } catch {
      // already stopped
    }
  }

  const toggleListening = () => {
    if (listening) {
      stopListening()
      announce("Voice command stopped.", { priority: 1 })
      return
    }

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition

    if (!SpeechRecognition) {
      setSupportError(
        "Voice recognition is not supported in this browser. Try Chrome or Edge."
      )
      return
    }

    setSupportError("")
    setTranscript("")

    const recognition = new SpeechRecognition()
    recognition.lang = "en-US"
    recognition.interimResults = true
    recognition.continuous = true
    recognitionRef.current = recognition

    recognition.onresult = (event) => {
      let interim = ""
      let final = ""
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const text = event.results[i][0].transcript
        if (event.results[i].isFinal) {
          final += text
        } else {
          interim += text
        }
      }
      if (final) {
        setTranscript(final.trim())
        setHistory((h) => [...h, { role: "user", text: final.trim() }].slice(-20))
        sendVoice(final.trim())
      } else if (interim) {
        setTranscript(interim)
      }
    }

    recognition.onend = () => {
      setListening(false)
      recognitionRef.current = null
    }

    recognition.onerror = (event) => {
      if (event.error !== "aborted" && event.error !== "no-speech") {
        setSupportError(`Recognition error: ${event.error}`)
        announce(`Voice recognition error: ${event.error}`, { priority: 1 })
      }
      setListening(false)
    }

    try {
      recognition.start()
      setListening(true)
      announce("Voice command listening.", { priority: 1 })
    } catch {
      setSupportError("Could not start voice recognition")
      announce("Could not start voice recognition.", { priority: 1 })
    }
  }

  const runCommand = (cmd) => {
    setHistory((h) => [...h, { role: "user", text: cmd }].slice(-20))

    // Handle TTS-related commands locally
    const lower = cmd.toLowerCase().trim()
    if (lower.includes("turn tts off") || lower.includes("disable tts") || lower === "mute") {
      setTTSEnabled(false)
      setHistory((h) => [...h, { role: "ai", text: "Text to speech disabled." }].slice(-20))
      return
    }
    if (lower.includes("turn tts on") || lower.includes("enable tts") || lower.includes("unmute")) {
      setTTSEnabled(true)
      // Short delay so the utterance fires after state updates
      setTimeout(() => announce("Text to speech enabled.", { priority: 0 }), 50)
      setHistory((h) => [...h, { role: "ai", text: "Text to speech enabled." }].slice(-20))
      return
    }

    announce(`Command: ${cmd}`, { priority: 1 })
    sendVoice(cmd)
  }

  return (
    <FeatureLayout title="HALO VISION — VOICE INTERFACE">
      <div className="flex items-center justify-between mb-8">
        <Link to="/home" className="inline-flex items-center gap-2 px-5 py-3 rounded-full border border-white/10 bg-white/5 hover:border-gold/30 hover:text-gold text-white/60 transition-all cursor-pointer">
          <ArrowLeft size={18} />
          <span className="text-sm font-medium">Back</span>
        </Link>
        <TTSButton />
      </div>
      <div className="max-w-3xl mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          className="relative inline-flex items-center justify-center mb-12"
        >
          <AnimatePresence>
            {listening &&
              [0, 1, 2].map((i) => (
                <motion.div
                  key={i}
                  initial={{ scale: 0.8, opacity: 0.5 }}
                  animate={{ scale: [1, 1.5 + i * 0.3, 1], opacity: [0.4, 0, 0.4] }}
                  exit={{ scale: 0.8, opacity: 0 }}
                  transition={{
                    duration: 1.5,
                    repeat: Infinity,
                    delay: i * 0.4,
                  }}
                  className="absolute w-24 h-24 rounded-full border border-gold/30"
                />
              ))}
          </AnimatePresence>

          <button
            onClick={toggleListening}
            aria-label={listening ? "Stop voice command" : "Start voice command"}
            className={`relative z-10 w-20 h-20 rounded-full flex items-center justify-center transition-all duration-500 ${
              listening
                ? "bg-gradient-to-br from-gold to-gold-dark shadow-[0_0_60px_rgba(255,179,71,0.3)]"
                : "bg-white/5 border border-white/10 hover:border-gold/30"
            }`}
          >
            {listening ? (
              <Mic size={32} className="text-black" />
            ) : (
              <MicOff size={32} className="text-white/60" />
            )}
          </button>
        </motion.div>

        <AnimatePresence mode="wait">
          {listening ? (
            <motion.div
              key="listening"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <h2 className="font-poppins text-2xl md:text-3xl font-bold text-white mb-2">
                Listening{dots}
              </h2>
              {transcript ? (
                <p className="text-gold/80 text-sm italic">"{transcript}"</p>
              ) : (
                <p className="text-white/50">Speak naturally - smart processing is active</p>
              )}

              <motion.div
                initial={{ width: 0 }}
                animate={{ width: "100%" }}
                transition={{ duration: 0.5 }}
                className="mt-8 h-px bg-gradient-to-r from-transparent via-gold/40 to-transparent"
              />
            </motion.div>
          ) : (
            <motion.div
              key="idle"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
            >
              <h2 className="font-poppins text-2xl md:text-3xl font-bold text-white mb-2">
                Voice Command
              </h2>
              <p className="text-white/50">Tap the microphone to begin</p>
            </motion.div>
          )}
        </AnimatePresence>

        {supportError && (
          <p className="mt-4 text-red-400 text-sm">{supportError}</p>
        )}

        {/* CONVERSATION HISTORY */}
        {history.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-12 text-left space-y-3 max-w-xl mx-auto"
          >
            {history.slice(-6).map((item, i) => (
              <GlassCard
                key={i}
                className={`p-4 flex items-start gap-3 ${
                  item.role === "user"
                    ? "border-gold/20"
                    : "border-white/10"
                }`}
              >
                {item.role === "user" ? (
                  <Mic size={16} className="text-gold mt-0.5 shrink-0" />
                ) : (
                  <Volume2 size={16} className="text-cyan-400 mt-0.5 shrink-0" />
                )}
                <p className="text-sm text-white/85 leading-relaxed">
                  {item.role === "user" ? (
                    <span className="text-gold/80">You: </span>
                  ) : (
                    <span className="text-cyan-400/80">SMART: </span>
                  )}
                  {item.text}
                </p>
              </GlassCard>
            ))}
          </motion.div>
        )}

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="mt-12"
        >
          <div className="flex items-center gap-2 justify-center mb-4">
            <Volume2 size={16} className="text-gold/60" />
            <span className="text-xs font-mono text-white/40">Try saying:</span>
          </div>
          <div className="flex flex-wrap justify-center gap-3">
            {commands.map((cmd, i) => (
              <motion.button
                key={cmd}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 0.6 + i * 0.1 }}
                onClick={() => runCommand(cmd)}
                aria-label={`Run command: ${cmd}`}
                className="px-4 py-2 text-sm text-white/60 border border-white/10 rounded-full hover:border-gold/30 hover:text-gold transition-all flex items-center gap-1.5"
              >
                {cmd}
                <ChevronRight size={14} className="text-gold/40" />
              </motion.button>
            ))}
          </div>

          {connected && (
            <p className="mt-6 text-[11px] font-mono text-green-400/70">
              ● SMART VOICE LINK ACTIVE
            </p>
          )}
        </motion.div>
      </div>
    </FeatureLayout>
  )
}
