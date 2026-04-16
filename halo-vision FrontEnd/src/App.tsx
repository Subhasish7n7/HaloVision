import { useState } from "react";
import "./App.css";
import { CameraView } from "./components/CameraView";
import Navbar from "./components/Navbar";
import Footer from "./components/Footer";
import "bootstrap/dist/css/bootstrap.min.css";
import "bootstrap/dist/js/bootstrap.bundle.min.js";
import { Routes, Route } from "react-router-dom";

import About from "./pages/About";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Why from "./pages/Why";

export default function App() {
  const [mode, setMode] = useState<
    "menu" | "camera" | "text" | "object" | "scene" | "voice"
  >("menu");

  const [detections, setDetections] = useState<any[]>([]);

  // 🔷 MAIN APP UI (MENU + HUD)
  const renderVisionApp = () => (
    <>
      {/* 🟢 MENU */}
      {mode === "menu" && (
        <div className="menu-container fade-in">
          <div className="menu-grid">

            <button className="halo-card full" onClick={() => setMode("voice")}>
              Voice Command
            </button>

            <button className="halo-card" onClick={() => setMode("camera")}>
              Camera
            </button>

            <button className="halo-card" onClick={() => setMode("text")}>
              Text Recognition
            </button>

            <button className="halo-card" onClick={() => setMode("object")}>
              Find My Object
            </button>

            <button className="halo-card" onClick={() => setMode("scene")}>
              Scene Description
            </button>

          </div>
        </div>
      )}

      {/* 🔵 HUD */}
      {mode !== "menu" && (
        <div className="hud fade-in">

          {/* SIDEBAR */}
          <div className="sidebar">
            {[
              { label: "Camera", icon: "📷", key: "camera" },
              { label: "Text Recognition", icon: "🧠", key: "text" },
              { label: "Find My Object", icon: "📡", key: "object" },
              { label: "Scene Description", icon: "🔍", key: "scene" },
              { label: "Voice Command", icon: "🎤", key: "voice" },
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
              {mode === "camera" ? (
                <CameraView setDetections={setDetections} />
              ) : (
                <p className="coming">🚧 Coming Soon...</p>
              )}
            </div>
          </div>

          {/* ✅ RIGHT PANEL */}
          <div className="panel">
            <h3>Detection Panel</h3>

            {detections.length === 0 ? (
              <p>No data yet</p>
            ) : (
              detections.map((d, i) => {
                const getColor = () => {
                  if (d.threat === 0 || d.threat === 1) return "cyan";
                  if (d.threat === 2) return "yellow";
                  if (d.threat === 3) return "red";
                  return "cyan";
                };

                const getIcon = () => {
                  const name = d.label?.toLowerCase();

                  if (name?.includes("person")) return "👤";
                  if (
                    name?.includes("car") ||
                    name?.includes("bike") ||
                    name?.includes("truck")
                  )
                    return "🚗";
                  if (name?.includes("chair")) return "🪑";

                  return "📦";
                };

                const color = getColor();

                return (
                  <div
                    key={i}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      background: "#020617",
                      border: `2px solid ${color}`,
                      borderRadius: "10px",
                      marginBottom: "10px",
                      overflow: "hidden",
                      boxShadow:
                        d.threat === 3 ? "0 0 15px red" : "none",
                    }}
                  >
                    {/* LEFT BAR */}
                    <div
                      style={{
                        width: "8px",
                        height: "100%",
                        backgroundColor: color,
                      }}
                    />

                    {/* CONTENT */}
                    <div style={{ padding: "10px" }}>
                      <div style={{ fontWeight: "bold", color }}>
                        {getIcon()} {d.label}
                      </div>

                      <div style={{ fontSize: "13px", color }}>
                        {d.message || "Detected"}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>

        </div>
      )}
    </>
  );

  return (
    <div className="app-layout">
      <Navbar />

      <div className="content">
        <Routes>
          <Route path="/" element={renderVisionApp()} />
          <Route path="/about" element={<About />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/why" element={<Why />} />
        </Routes>
      </div>

      <Footer />
    </div>
  );
}