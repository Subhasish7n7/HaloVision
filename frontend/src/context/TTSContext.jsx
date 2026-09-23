/**
 * TTSContext — React context providing TTS state + announce to all components.
 *
 * Usage:
 *   const { enabled, toggle, announce } = useTTS()
 *   announce("Button pressed")
 *   toggle()
 */

import { createContext, useContext, useCallback, useEffect, useState } from "react"
import * as tts from "../services/tts"

const TTSContext = createContext(null)

export function TTSProvider({ children }) {
  const [enabled, setEnabledState] = useState(tts.isEnabled)

  useEffect(() => {
    return tts.onEnabledChange((next) => setEnabledState(next))
  }, [])

  const toggle = useCallback(() => {
    tts.toggle()
  }, [])

  const setEnabled = useCallback((val) => {
    tts.setEnabled(val)
  }, [])

  const announce = useCallback((text, opts) => {
    return tts.announce(text, opts)
  }, [])

  const cancel = useCallback(() => {
    tts.cancel()
  }, [])

  return (
    <TTSContext.Provider value={{ enabled, toggle, setEnabled, announce, cancel }}>
      {children}
    </TTSContext.Provider>
  )
}

export function useTTS() {
  const ctx = useContext(TTSContext)
  if (!ctx) {
    // Graceful fallback — if provider is missing, TTS is off
    return {
      enabled: false,
      toggle: () => {},
      setEnabled: () => {},
      announce: () => false,
      cancel: () => {},
    }
  }
  return ctx
}
