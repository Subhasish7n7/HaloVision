/**
 * Centralized Text-to-Speech service for HaloVision.
 *
 * Provides:
 *   - announce(text, options)  — speak a message if TTS is enabled
 *   - enabled / setEnabled()   — ON/OFF state, persisted in localStorage
 *   - cancel()                 — stop current speech immediately
 *
 * All UI announcements should go through announce() — never call
 * window.speechSynthesis directly from components.
 *
 * Persistence: localStorage key "halo_tts_enabled" (true/false).
 * Default: true (TTS ON on first visit).
 */

const STORAGE_KEY = "halo_tts_enabled"
const PITCH = 1
const RATE = 1

let currentPriority = 0
let voicesLoaded = false
let enabledListeners = []

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

function readInitialEnabled() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === null) return true // default ON
    return stored !== "false"
  } catch {
    return true
  }
}

let _enabled = readInitialEnabled()

export function isEnabled() {
  return _enabled
}

export function setEnabled(value) {
  const next = Boolean(value)
  if (next === _enabled) return
  _enabled = next
  try {
    localStorage.setItem(STORAGE_KEY, String(next))
  } catch { /* storage full or private mode — ignore */ }
  if (!next) cancel()
  for (const fn of enabledListeners) fn(next)
}

export function toggle() {
  setEnabled(!_enabled)
}

export function onEnabledChange(fn) {
  enabledListeners.push(fn)
  return () => {
    enabledListeners = enabledListeners.filter((f) => f !== fn)
  }
}

// ---------------------------------------------------------------------------
// Voice selection (matches existing browserSpeech.js preferences)
// ---------------------------------------------------------------------------

const pickVoice = () => {
  if (!voicesLoaded) voicesLoaded = true
  const voices = window.speechSynthesis?.getVoices?.() || []
  return (
    voices.find(
      (v) => /en[-_](US|GB)/i.test(v.lang) && /aria|jenny|susan|female|zira/i.test(v.name)
    ) ||
    voices.find((v) => v.lang && v.lang.toLowerCase().startsWith("en")) ||
    null
  )
}

// ---------------------------------------------------------------------------
// Cancel
// ---------------------------------------------------------------------------

export function cancel() {
  currentPriority = 0
  try {
    window.speechSynthesis?.cancel?.()
  } catch { /* ignore */ }
}

// ---------------------------------------------------------------------------
// announce
// ---------------------------------------------------------------------------

/**
 * Speak a message if TTS is enabled.
 *
 * @param {string} text       - The text to speak
 * @param {object} [opts]
 * @param {number} [opts.priority=1]  - Higher preempts lower (0=highest)
 * @param {boolean} [opts.force=false] - Speak even if TTS is OFF (used for critical alerts)
 * @returns {boolean} true if speech was queued
 */
export function announce(text, { priority = 1, force = false } = {}) {
  if (!text || typeof window === "undefined") return false

  if (!force && !_enabled) return false

  if (!window.speechSynthesis) return false

  // Higher-priority announcements preempt lower ones
  if (priority >= currentPriority) {
    window.speechSynthesis.cancel()
    currentPriority = priority
  } else {
    return false
  }

  const utterance = new SpeechSynthesisUtterance(text)
  const voice = pickVoice()
  if (voice) utterance.voice = voice
  utterance.rate = RATE
  utterance.pitch = PITCH

  utterance.onend = () => {
    currentPriority = 0
  }
  utterance.onerror = () => {
    currentPriority = 0
  }

  window.speechSynthesis.speak(utterance)
  return true
}
