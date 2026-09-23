import { useEffect, useState } from "react"
import { FilesetResolver, HandLandmarker } from "@mediapipe/tasks-vision"
import { analyzeFingers } from "../utils/handGeometry"
import { detectGesture } from "../utils/gestures"

/**
 * Internal probe page (no nav link): runs the REAL production chain —
 * MediaPipe HandLandmarker (local wasm + task) -> handGeometry ->
 * gestureRecognition — against a real hand photograph. Used to verify
 * gesture detection headlessly (Chrome --headless --dump-dom).
 */
export default function GestureTestFeature() {
  const [lines, setLines] = useState(["loading…"])

  useEffect(() => {
    let cancelled = false
    const out = []

    ;(async () => {
      try {
        const wasm = `${import.meta.env.BASE_URL}mediapipe/wasm`
        const task = `${import.meta.env.BASE_URL}mediapipe/models/hand_landmarker.task`
        const imgUrl = `${import.meta.env.BASE_URL}mediapipe/test-hand.jpg`

        const fileset = await FilesetResolver.forVisionTasks(wasm)
        out.push("WASM loaded")
        const lm = await HandLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: task, delegate: "CPU" },
          runningMode: "IMAGE",
          numHands: 2,
        })
        out.push("MODEL LOADED (CPU delegate, headless-safe)")

        const img = new Image()
        img.src = imgUrl
        await img.decode()
        out.push(`image ${img.naturalWidth}x${img.naturalHeight}`)

        const res = lm.detect(img)
        const count = res.landmarks?.length ?? 0
        out.push(`HANDS DETECTED: ${count}`)

        ;(res.landmarks || []).forEach((lmks, i) => {
          const hand = lmks.map((p) => ({ x: p.x, y: p.y, z: p.z || 0 }))
          const { fingers } = analyzeFingers(hand)
          const g = detectGesture(hand, fingers)
          const handed = res.handednesses?.[i]?.[0]?.categoryName || "?"
          const ext = Object.entries(fingers)
            .map(([n, f]) => `${n}:${f.angle.toFixed(0)}${f.extended ? "up" : "dn"}`)
            .join(" ")
          out.push(`HAND ${i + 1} [${handed}] gesture=${g.name} conf=${g.confidence}`)
          out.push(`  fingers ${ext}`)
        })
      } catch (e) {
        out.push("ERROR: " + (e?.message || String(e)))
      }

      if (!cancelled) {
        document.title = out.join(" | ").slice(0, 400)
        setLines(out)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div style={{ padding: 24, fontFamily: "monospace", whiteSpace: "pre-wrap", color: "#0f0", background: "#000", minHeight: "100vh" }}>
      <div id="out">{lines.join("\n")}</div>
    </div>
  )
}