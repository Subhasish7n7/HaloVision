import { useState, useEffect } from "react";
import "./App.css";
import { CameraView } from "./components/CameraView";
import Navbar from "./components/Navbar";
import Footer from "./components/Footer";
import { Routes, Route } from "react-router-dom";

import About from "./pages/About";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Why from "./pages/Why";

import { socketService } from "./services/socket";

export default function App() {
  const [mode, setMode] = useState<
    "menu" | "camera" | "text" | "object" | "scene" | "voice"
  >("menu");

  const [detections, setDetections] = useState<any[]>([]);
  const [searchText, setSearchText] = useState("");

  // =========================
  // SOCKET CONNECTION
  // =========================
  useEffect(() => {
    socketService.connect((data) => {
      if (data.type === "detections") {
        setDetections(data.data);
      }
    });
  }, []);

  // =========================
  // MODE CHANGE
  // =========================
  const changeMode = (newMode: any) => {
    setMode(newMode);

    if (newMode !== "menu") {
      socketService.sendMode(newMode);
    }

    if (newMode !== "object") {
      socketService.sendSearch("");
      setSearchText("");
    }
  };

  // =========================
  // 🔥 THREAT LOGIC
  // =========================
  const threatCount = detections.length;
  const isThreat = threatCount >= 3;

  // =========================
  // MAIN UI
  // =========================
  const renderVisionApp = () => (
    <>
      {/* MENU */}
      {mode === "menu" && (
        <div className="menu-container">
          <div className="menu-grid">
            <button className="halo-card full" onClick={() => changeMode("voice")}>
              Voice Command
            </button>

            <button className="halo-card" onClick={() => changeMode("camera")}>
              Navigation
            </button>

            <button className="halo-card" onClick={() => changeMode("text")}>
              Threat
            </button>

            <button className="halo-card" onClick={() => changeMode("object")}>
              Search
            </button>

            <button className="halo-card" onClick={() => changeMode("scene")}>
              Scene Description
            </button>
          </div>
        </div>
      )}

      {/* MAIN */}
      {mode !== "menu" && (
        <div className="hud">

          {/* SIDEBAR */}
          <div className="sidebar">
            {[
              { label: "Navigation", icon: "📷", key: "camera" },
              { label: "Threat", icon: "🧠", key: "text" },
              { label: "Search", icon: "📡", key: "object" },
              { label: "Scene", icon: "🔍", key: "scene" },
              { label: "Voice", icon: "🎤", key: "voice" },
            ].map((item, i) => (
              <div
                key={i}
                className={`vision-btn ${mode === item.key ? "active" : ""}`}
                onClick={() => changeMode(item.key)}
              >
                <div className="icon">{item.icon}</div>
                <div className="label">{item.label}</div>
              </div>
            ))}

            <div
              className="vision-btn"
              onClick={() => changeMode("menu")}
              style={{ borderColor: "red", color: "red" }}
            >
              <div className="icon">←</div>
              <div className="label">Back</div>
            </div>
          </div>

          {/* CENTER */}
          <div className="center">

            {/* CAMERA */}
            <div className="camera-box">
              {(mode === "camera" || mode === "object" || mode === "text") ? (
                <CameraView
                  detections={detections}
                  active={mode === "camera" || mode === "object" || mode === "text"}
                />
              ) : (
                <p className="coming">🚧 Coming Soon...</p>
              )}
            </div>

            {/* SEARCH */}
            {mode === "object" && (
              <div className="search-box">
                <input
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  placeholder="Search object"
                  className="search-input"
                />
                <button
                  className="search-btn"
                  onClick={() => socketService.sendSearch(searchText)}
                >
                  Find
                </button>
              </div>
            )}

          </div>

          {/* PANEL */}
          <div className="panel">
            <h3>Detection Panel</h3>

            {/* 🔥 THREAT STATUS */}
            {mode === "text" && (
              <div>
                {isThreat ? (
                  <p style={{ color: "red", fontWeight: "bold" }}>
                    ⚠️ Threat detected ({threatCount})
                  </p>
                ) : (
                  <p style={{ color: "green" }}>
                    ✅ No threat detected
                  </p>
                )}
              </div>
            )}

            {detections.length === 0 ? (
              <p>No data</p>
            ) : (
              detections.map((d, i) => (
                <div key={i}>{d.label}</div>
              ))
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