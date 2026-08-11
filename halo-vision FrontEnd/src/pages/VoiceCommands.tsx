import { useState, useEffect } from "react";
import "./voice-commands.css";

type VoiceCommand = {
  id: number;
  command_text: string;
  action: string | null;
  success: number | null;
  timestamp: string;
};

export default function VoiceCommands() {
  const [commands, setCommands] = useState<VoiceCommand[]>([]);

  useEffect(() => {
    const token = localStorage.getItem("token");
    fetch("http://localhost:8000/api/voice-commands", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((d) => setCommands(d))
      .catch(() => {});
  }, []);

  return (
    <div className="vc-container">
      <div className="vc-header">
        <h2>Voice Commands</h2>
        <p>History of voice commands processed</p>
      </div>

      {commands.length === 0 ? (
        <p className="vc-empty">No voice commands recorded</p>
      ) : (
        <div className="vc-list">
          {commands.map((c) => (
            <div key={c.id} className="vc-card">
              <div className="vc-card-top">
                <span className="vc-command">🎤 {c.command_text}</span>
                <span className="vc-status">
                  {c.success === 1 ? "✅" : "❌"}
                </span>
              </div>
              <div className="vc-card-bottom">
                {c.action && <span>Action: {c.action}</span>}
                <span className="vc-time">
                  {new Date(c.timestamp).toLocaleString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
