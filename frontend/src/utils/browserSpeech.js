/**
 * Browser-native speech fallback.
 *
 * Server-side edge-tts synthesis can be blocked by the network (403 from
 * speech.platform.bing.com); when that happens the backend falls back to
 * `speech_text` messages. This uses the browser's SpeechSynthesis API so
 * announcements still become real voice — zero extra dependencies.
 *
 * This module now delegates to the centralized TTS service for the
 * enabled/disabled check. If TTS is OFF, browserSpeak returns without
 * speaking.
 */

import { isEnabled } from "../services/tts"

let currentPriority = 0
let voicesLoaded = false

const pickVoice = () => {
  if (!voicesLoaded) {
    voicesLoaded = true
  }
  const voices = window.speechSynthesis?.getVoices?.() || []
  return (
    voices.find((v) => /en[-_](US|GB)/i.test(v.lang) && /aria|jenny|susan|female|zira/i.test(v.name)) ||
    voices.find((v) => v.lang && v.lang.toLowerCase().startsWith("en")) ||
    null
  )
}

export function browserSpeak(text, { priority = 1 } = {}) {
  if (!text || typeof window === "undefined" || !window.speechSynthesis) return
  if (!isEnabled()) return

  // Higher-priority announcements preempt quieter ones (mirrors the
  // backend audio interrupt policy).
  if (priority >= currentPriority) {
    window.speechSynthesis.cancel()
    currentPriority = priority
  } else {
    return // lower priority than something currently being said — skip
  }

  const utterance = new SpeechSynthesisUtterance(text)
  const voice = pickVoice()
  if (voice) utterance.voice = voice
  utterance.rate = 1
  utterance.onend = () => {
    currentPriority = 0
  }
  utterance.onerror = () => {
    currentPriority = 0
  }

  window.speechSynthesis.speak(utterance)
}
