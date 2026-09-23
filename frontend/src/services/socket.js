class SocketService {
  ws = null
  baseUrl = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws"
  isConnecting = false
  reconnectTimer = null
  onMessageCallback = null
  lastFrameTime = 0
  disposed = true

  get url() {
    const token =
      localStorage.getItem("halo_token") || sessionStorage.getItem("halo_token")
    if (!token) return this.baseUrl
    const sep = this.baseUrl.includes("?") ? "&" : "?"
    return `${this.baseUrl}${sep}token=${encodeURIComponent(token)}`
  }

  connect(onMessage, onClose) {
    this.onMessageCallback = onMessage
    this.onCloseCallback = onClose || null
    this.disposed = false

    if (this.ws?.readyState === WebSocket.OPEN) return
    if (this.isConnecting) return

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }

    this.isConnecting = true
    const ws = new WebSocket(this.url)
    this.ws = ws
    ws.binaryType = "arraybuffer"

    ws.onopen = () => {
      if (this.disposed) {
        ws.close()
        return
      }
      this.isConnecting = false
      if (this._pendingMode) {
        this.sendMode(this._pendingMode)
        this._pendingMode = null
      }
    }

    ws.onerror = () => {
      if (this.ws === ws) this.isConnecting = false
    }

    ws.onmessage = (event) => {
      if (this.ws !== ws) return
      try {
        const text =
          typeof event.data === "string"
            ? event.data
            : new TextDecoder().decode(event.data)
        const data = JSON.parse(text)
        if (this.onMessageCallback) {
          this.onMessageCallback(data)
        }
      } catch (e) {
        // ignore parse errors
      }
    }

    ws.onclose = () => {
      if (this.ws !== ws) return
      this.ws = null
      this.isConnecting = false
      this.onCloseCallback?.()

      if (!this.disposed && this.onMessageCallback && !this.reconnectTimer) {
        this.reconnectTimer = setTimeout(() => {
          this.reconnectTimer = null
          if (!this.disposed && this.onMessageCallback) {
            this.connect(this.onMessageCallback, this.onCloseCallback)
          }
        }, 2000)
      }
    }
  }

  sendFrame(buffer) {
    const now = Date.now()
    if (now - this.lastFrameTime < 100) return
    this.lastFrameTime = now

    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(buffer)
    }
  }

  sendMode(mode) {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      this._pendingMode = mode
      return
    }

    const modeMap = {
      camera: "navigation",
      text: "threat",
      object: "search",
      scene: "description",
      voice: "voice",
    }

    this.ws.send(
      JSON.stringify({
        type: "mode",
        data: modeMap[mode] || mode,
      })
    )
  }

  sendSearch(text) {
    if (this.ws?.readyState !== WebSocket.OPEN) return

    this.ws.send(
      JSON.stringify({
        type: "search",
        data: text.toLowerCase(),
      })
    )
  }

  sendVoice(text) {
    if (this.ws?.readyState !== WebSocket.OPEN) return

    this.ws.send(
      JSON.stringify({
        type: "voice",
        data: text,
      })
    )
  }

  sendGestureCommand(gesture) {
    if (this.ws?.readyState !== WebSocket.OPEN) return

    this.ws.send(
      JSON.stringify({
        type: "gesture_command",
        data: gesture,
      })
    )
  }

  disconnect() {
    this.disposed = true

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }

    // Only close an established socket. Aborting a CONNECTING socket
    // triggers a browser error, and the "disposed" flag handles that case.
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.close()
    }
    this.ws = null
    this.isConnecting = false
    this.onMessageCallback = null
  }
}

export const socketService = new SocketService()
