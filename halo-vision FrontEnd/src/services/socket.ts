class SocketService {
  private ws: WebSocket | null = null;
  private url = "ws://localhost:8000/ws";
  private isConnecting = false;
  private reconnectTimer: any = null;

  // =========================
  // CONNECT
  // =========================
  connect(onMessage: (data: any) => void) {
    if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) return;

    this.isConnecting = true;

    this.ws = new WebSocket(this.url);
    this.ws.binaryType = "arraybuffer";

    this.ws.onopen = () => {
      this.isConnecting = false;

      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const text =
          typeof event.data === "string"
            ? event.data
            : new TextDecoder().decode(event.data);

        const data = JSON.parse(text);

        // 🔥 no speech here (backend handles it)
        onMessage(data);
      } catch {}
    };

    this.ws.onclose = () => {
      this.ws = null;
      this.isConnecting = false;

      if (!this.reconnectTimer) {
        this.reconnectTimer = setTimeout(() => {
          this.connect(onMessage);
          this.reconnectTimer = null;
        }, 2000);
      }
    };
  }

  // =========================
  // SEND FRAME
  // =========================
  sendFrame(buffer: ArrayBuffer) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(buffer);
    }
  }

  // =========================
  // 🔥 SEND MODE (STRING BASED)
  // =========================
  sendMode(mode: string) {
    if (this.ws?.readyState !== WebSocket.OPEN) return;

    // 🔥 map frontend → backend names
    const modeMap: any = {
      camera: "navigation",
      text: "threat",
      object: "search",
      scene: "description",
      voice: "voice",
    };

    const finalMode = modeMap[mode] || mode;

    this.ws.send(
      JSON.stringify({
        type: "mode",
        data: finalMode,
      })
    );

    console.log("📤 MODE:", finalMode);
  }

  // =========================
  // SEND SEARCH
  // =========================
  sendSearch(text: string) {
    if (this.ws?.readyState !== WebSocket.OPEN) return;

    this.ws.send(
      JSON.stringify({
        type: "search",
        data: text.toLowerCase(),
      })
    );

    console.log("🔍 SEARCH:", text);
  }

  // =========================
  // DISCONNECT
  // =========================
  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    this.ws?.close();
    this.ws = null;
    this.isConnecting = false;
  }
}

export const socketService = new SocketService();