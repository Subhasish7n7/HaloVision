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

        // 🔊 SPEECH
        if (data.type === "speech_text") {
          const utter = new SpeechSynthesisUtterance(data.data);
          speechSynthesis.speak(utter);
        }

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
  // 🔥 SEND MODE (ALIGNED)
  // =========================
  sendMode(mode: string) {
    if (this.ws?.readyState !== WebSocket.OPEN) return;

    const payload = {
      navigation_mode: mode === "camera",
      threat_mode: mode === "text",
      search_mode: mode === "object",
      description_mode: mode === "scene",
      muted: false,
    };

    this.ws.send(
      JSON.stringify({
        type: "mode",
        data: payload,
      })
    );
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