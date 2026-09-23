/**
 * Shared object-fit: cover coordinate transform.
 *
 * The live video is rendered with `object-fit: cover`, so normalized / raw
 * frame coordinates are NOT a straight percentage of the container. These
 * helpers compute the same scale + crop offsets used by CameraView's box
 * rendering, so every overlay (detection boxes, hand landmarks, finger
 * boxes) lines up with the actual video pixels.
 */

export function coverLayout(video, container) {
  const vw = video?.videoWidth || 640
  const vh = video?.videoHeight || 480
  const cw = container?.clientWidth || 0
  const ch = container?.clientHeight || 0

  if (!cw || !ch) {
    return { vw, vh, scale: 0, offsetX: 0, offsetY: 0 }
  }

  // cover: scale up until BOTH dimensions fill the container
  const scale = Math.max(cw / vw, ch / vh)
  const displayedW = vw * scale
  const displayedH = vh * scale

  return {
    vw,
    vh,
    scale,
    offsetX: (cw - displayedW) / 2,
    offsetY: (ch - displayedH) / 2,
  }
}

/**
 * Map a bounding box in *normalized* coordinates (0..1) to absolute px on
 * screen given the video + container. `padding` is an extra normalized inset
 * applied on all four sides (e.g. so a finger box never touches its joints).
 */
export function coverBox(normalizedBbox, video, container, padding = 0) {
  const { vw, vh, scale, offsetX, offsetY } = coverLayout(video, container)
  const [x1, y1, x2, y2] = normalizedBbox

  const left = x1 * vw * scale + offsetX - padding * vw * scale
  const top = y1 * vh * scale + offsetY - padding * vh * scale
  const right = x2 * vw * scale + offsetX + padding * vw * scale
  const bottom = y2 * vh * scale + offsetY + padding * vh * scale

  return {
    left: Math.max(0, left),
    top: Math.max(0, top),
    width: Math.max(0, right - left),
    height: Math.max(0, bottom - top),
  }
}

/** Map a normalized point to absolute px on screen. */
export function coverPoint(nx, ny, video, container) {
  const { vw, vh, scale, offsetX, offsetY } = coverLayout(video, container)
  return {
    x: nx * vw * scale + offsetX,
    y: ny * vh * scale + offsetY,
  }
}