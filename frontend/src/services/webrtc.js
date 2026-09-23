/**
 * WebRTCClient — streams the live camera track to the HaloVision backend
 * over a real WebRTC PeerConnection (RTP, no per-frame JPEG round-trip).
 *
 * Signaling: a tiny WebSocket to `/rtc` exchanges SDP offer/answer and ICE
 * candidates. Detections + audio still arrive on the existing `/ws` socket.
 */

const SIGNAL_URL =
  import.meta.env.VITE_RTC_URL || "ws://localhost:8000/rtc"

function getSignalUrl() {
  const token =
    localStorage.getItem("halo_token") || sessionStorage.getItem("halo_token")
  if (!token) return SIGNAL_URL
  const sep = SIGNAL_URL.includes("?") ? "&" : "?"
  return `${SIGNAL_URL}${sep}token=${encodeURIComponent(token)}`
}

export const WEBRTC_SUPPORTED = typeof RTCPeerConnection !== "undefined"

const ICE_SERVERS = [
  { urls: "stun:stun.l.google.com:19302" },
  { urls: "stun:stun1.l.google.com:19302" },
]

class WebRTCClient {
  pc = null
  signal = null
  connected = false
  _ready = null
  _timeout = null
  _stream = null

  get isConnected() {
    return this.connected
  }

  /**
   * Open a peer connection and stream `stream`'s video track to the backend.
   * Resolves once the RTCPeerConnection reaches "connected".
   */
  connect(stream) {
    if (!WEBRTC_SUPPORTED) {
      return Promise.reject(new Error("WebRTC not supported in this browser"))
    }
    if (this.connected || this.pc) return Promise.resolve(true)

    this._stream = stream
    this.connected = false
    this.pc = new RTCPeerConnection({ iceServers: ICE_SERVERS })

    stream.getVideoTracks().forEach((track) => {
      this.pc.addTrack(track, stream)
    })

    this.pc.onconnectionstatechange = () => {
      const state = this.pc.connectionState
      if (state === "connected") {
        this.connected = true
        this._ready?.resolve(true)
      } else if (state === "failed" || state === "closed") {
        this.connected = false
        if (this._ready && !this._ready.settled) {
          this._ready.reject(new Error(`RTC ${state}`))
        }
      }
    }

    return this._negotiate()
  }

  _negotiate() {
    return new Promise(async (resolve, reject) => {
      this._ready = { resolve, reject, settled: false }
      const settle = (fn, val) => {
        if (!this._ready || this._ready.settled) return
        this._ready.settled = true
        clearTimeout(this._timeout)
        fn(val)
      }

      this._timeout = setTimeout(() => {
        settle(reject, new Error("RTC connect timeout"))
      }, 8000)

      try {
        const offer = await this.pc.createOffer()
        await this.pc.setLocalDescription(offer)
      } catch (err) {
        settle(reject, err)
        return
      }

      const ws = new WebSocket(getSignalUrl())
      this.signal = ws

      ws.onopen = () => {
        ws.send(JSON.stringify({ type: "offer", sdp: this.pc.localDescription.sdp }))
      }

      ws.onmessage = (e) => {
        let msg
        try {
          msg = JSON.parse(e.data)
        } catch {
          return
        }
        if (msg.type === "answer" && msg.sdp) {
          this.pc.setRemoteDescription({ type: "answer", sdp: msg.sdp }).catch(() => {})
        } else if (msg.type === "ice" && msg.candidate) {
          this.pc.addIceCandidate(msg.candidate).catch(() => {})
        }
      }

      ws.onerror = () => settle(reject, new Error("RTC signaling error"))
      ws.onclose = () => {
        if (!this.connected) settle(reject, new Error("RTC signaling closed"))
      }

      this.pc.onicecandidate = (e) => {
        if (e.candidate && ws.readyState === WebSocket.OPEN) {
          ws.send(
            JSON.stringify({
              type: "ice",
              candidate: {
                candidate: e.candidate.candidate,
                sdpMid: e.candidate.sdpMid,
                sdpMLineIndex: e.candidate.sdpMLineIndex,
              },
            })
          )
        }
      }

      // resolve on connection state
      const prevSettle = settle
      this._ready.resolve = (v) => prevSettle(resolve, v)
      this._ready.reject = (e) => prevSettle(reject, e)
    })
  }

  stop() {
    if (this.signal) {
      try {
        this.signal.close()
      } catch {}
    }
    if (this.pc) {
      try {
        this.pc.close()
      } catch {}
    }
    this.pc = null
    this.signal = null
    this.connected = false
    this._stream = null
    this._ready = null
    clearTimeout(this._timeout)
  }
}

export const webrtcClient = new WebRTCClient()