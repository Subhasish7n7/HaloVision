import { useState } from "react";
import "./App.css";
import { CameraView } from "./components/CameraView";

export default function App() {
  const [mode, setMode] = useState<
    "menu" | "camera" | "text" | "object" | "scene" | "voice"
  >("menu");

  const [detections, setDetections] = useState<any[]>([]);

  // =========================
  // 🟢 MENU
  // =========================
  if (mode === "menu") {
    return (
      <div className="menu-container fade-in">
        <h1 className="title">Halo Vision</h1>

        <div className="menu-grid">

          <button className="card full" onClick={() => setMode("voice")}>
            Voice Command
          </button>

          <button className="card" onClick={() => setMode("camera")}>
            Camera
          </button>

          <button className="card" onClick={() => setMode("text")}>
            Text Recognition
          </button>

          <button className="card" onClick={() => setMode("object")}>
            Find My Object
          </button>

          <button className="card" onClick={() => setMode("scene")}>
            Scene Description
          </button>

        </div>
      </div>
    );
  }

  // =========================
  // 🔵 HUD
  // =========================
  return (
    <div className="hud fade-in">

      {/* SIDEBAR */}
      <div className="sidebar">

        {[
          { label: "Camera", icon: "📷", key: "navigation" },
          { label: "text recognition", icon: "🧠", key: "text" },
          { label: "find my object", icon: "📡", key: "search" },
          { label: "scene description", icon: "🔒", key: "scene" },
          { label: "voice command", icon: "🎤", key: "command" },
        ].map((item, i) => (
          <div
            key={i}
            className={`vision-btn ${mode === item.key ? "active" : ""}`}
            onClick={() => setMode(item.key as any)}
          >
            <div className="icon">{item.icon}</div>
            <div className="label">{item.label}</div>
          </div>
        ))}

        {/* BACK */}
        <div
          className="vision-btn"
          onClick={() => setMode("menu")}
          style={{ borderColor: "red", color: "red" }}
        >
          <div className="icon">←</div>
          <div className="label">Back</div>
        </div>

      </div>

      {/* CENTER */}
      <div className="center">
        <div className="camera-box">

          {mode === "camera" && (
            <CameraView setDetections={setDetections} />
          )}

          {mode !== "camera" && (
            <p className="coming">🚧 Coming Soon...</p>
          )}

        </div>
      </div>

      {/* RIGHT PANEL */}
      <div className="panel">
        <h3>Detection Panel</h3>

        {detections.length === 0 ? (
          <p>No data yet</p>
        ) : (
          detections.map((d, i) => (
            <div
              key={i}
              style={{
                border: `1px solid ${
                  d.label?.toLowerCase().includes("person")
                    ? "red"
                    : "cyan"
                }`,
                color: d.label?.toLowerCase().includes("person")
                  ? "red"
                  : "cyan",
                padding: "6px",
                marginBottom: "6px",
                borderRadius: "6px",
              }}
            >
              {d.label}
            </div>
          ))
        )}
      </div>

    </div>
  );
}