import { useState, useEffect } from "react";

export default function Settings() {
  const [ttsSpeed, setTtsSpeed] = useState(1);
  const [defaultMode, setDefaultMode] = useState("navigation");
  const [voice, setVoice] = useState("default");
  const [theme, setTheme] = useState("dark");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("token");
    fetch("http://localhost:8000/api/preferences", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((d) => {
        setTtsSpeed(d.tts_speed);
        setDefaultMode(d.default_mode);
        setVoice(d.voice);
        setTheme(d.theme);
      })
      .catch(() => {});
  }, []);

  const handleSave = async () => {
    const token = localStorage.getItem("token");
    try {
      const res = await fetch("http://localhost:8000/api/preferences", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ tts_speed: ttsSpeed, default_mode: defaultMode, voice, theme }),
      });
      if (res.ok) {
        setMsg("Preferences saved ✅");
      } else {
        setMsg("Failed to save");
      }
    } catch {
      setMsg("Server not reachable");
    }
  };

  const modes = ["navigation", "threat", "search", "description", "voice"];
  const voices = ["default", "en-US-AriaNeural", "en-US-GuyNeural", "en-US-JennyNeural"];

  return (
    <div style={styles.container}>
      <div style={styles.box}>
        <h2 style={styles.title}>Settings</h2>

        <label style={styles.label}>TTS Speed</label>
        <input
          type="range"
          min={1}
          max={5}
          value={ttsSpeed}
          onChange={(e) => setTtsSpeed(Number(e.target.value))}
          style={styles.range}
        />
        <span style={{ color: "cyan", fontSize: "14px" }}>{ttsSpeed}x</span>

        <label style={styles.label}>Default Mode</label>
        <select
          value={defaultMode}
          onChange={(e) => setDefaultMode(e.target.value)}
          style={styles.input}
        >
          {modes.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>

        <label style={styles.label}>Voice</label>
        <select
          value={voice}
          onChange={(e) => setVoice(e.target.value)}
          style={styles.input}
        >
          {voices.map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>

        <label style={styles.label}>Theme</label>
        <select
          value={theme}
          onChange={(e) => setTheme(e.target.value)}
          style={styles.input}
        >
          <option value="dark">Dark</option>
          <option value="light">Light</option>
        </select>

        <button style={styles.button} onClick={handleSave}>
          Save Preferences
        </button>

        {msg && <p style={styles.msg}>{msg}</p>}
      </div>
    </div>
  );
}

const styles: any = {
  container: {
    height: "100vh",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    background: "black",
  },
  box: {
    width: "400px",
    padding: "40px",
    borderRadius: "20px",
    background: "rgba(5,8,22,0.9)",
    border: "1.5px solid cyan",
    boxShadow: "0 0 25px rgba(0,255,255,0.2)",
    textAlign: "center",
  },
  title: {
    color: "cyan",
    marginBottom: "25px",
  },
  label: {
    display: "block",
    color: "cyan",
    textAlign: "left",
    marginTop: "15px",
    marginBottom: "5px",
    fontSize: "14px",
  },
  input: {
    width: "100%",
    padding: "12px",
    marginBottom: "5px",
    borderRadius: "8px",
    border: "1.5px solid cyan",
    background: "black",
    color: "cyan",
    outline: "none",
  },
  range: {
    width: "100%",
    accentColor: "cyan",
  },
  button: {
    width: "100%",
    padding: "12px",
    marginTop: "20px",
    borderRadius: "25px",
    border: "none",
    background: "linear-gradient(135deg, cyan, #00ffff)",
    color: "black",
    fontWeight: "bold",
    cursor: "pointer",
  },
  msg: {
    color: "lightgreen",
    marginTop: "12px",
    fontSize: "14px",
  },
};
