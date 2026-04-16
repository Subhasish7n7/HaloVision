class SocketService {
  private ws: WebSocket | null = null;

  connect(onMessage: (data: any) => void) {
    if (this.ws) return;

    this.ws = new WebSocket("ws://127.0.0.1:8000/ws");
    this.ws.binaryType = "arraybuffer";

    this.ws.onopen = () => {
      console.log("✅ WebSocket connected");
    };

    this.ws.onmessage = (event) => {
      try {
        const text =
          typeof event.data === "string"
            ? event.data
            : new TextDecoder().decode(event.data);

        const data = JSON.parse(text);
        if (data?.type === "detections") {
          console.log("📦 DETECTIONS:", data.data);
        }

        // console.log("📩 WS:", data);

        onMessage(data);
      } catch (e) {
        console.error("❌ WS parse error:", e);
      }
    };

    this.ws.onclose = () => {
      console.log("❌ WebSocket disconnected");
      this.ws = null;

      setTimeout(() => this.connect(onMessage), 1000);
    };

    this.ws.onerror = (err) => {
      console.error("❌ WebSocket error:", err);
    };
  }

  sendFrame(buffer: ArrayBuffer) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(buffer);
  }

  disconnect() {
    this.ws?.close();
    this.ws = null;
  }
}

export const socketService = new SocketService();