import { useState, useEffect } from "react";
import "./sessions.css";

type Session = {
  id: number;
  active_mode: string | null;
  frames_processed: number;
  start_time: string;
  end_time: string | null;
};

export default function Sessions() {
  const [sessions, setSessions] = useState<Session[]>([]);

  useEffect(() => {
    const token = localStorage.getItem("token");
    fetch("http://localhost:8000/api/sessions", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.json())
      .then((data) => setSessions(data))
      .catch(() => {});
  }, []);

  const formatDuration = (start: string, end: string | null) => {
    const s = new Date(start).getTime();
    const e = end ? new Date(end).getTime() : Date.now();
    const diff = Math.floor((e - s) / 1000);
    if (diff < 60) return `${diff}s`;
    return `${Math.floor(diff / 60)}m ${diff % 60}s`;
  };

  const modeIcon = (mode: string | null) => {
    const map: any = {
      navigation: "📷",
      threat: "🧠",
      search: "📡",
      description: "🔍",
      voice: "🎤",
    };
    return map[mode || ""] || "❓";
  };

  return (
    <div className="sessions-container">
      <div className="sessions-header">
        <h2>User Sessions</h2>
        <p>History of your usage sessions</p>
      </div>

      {sessions.length === 0 ? (
        <p className="sessions-empty">No sessions recorded</p>
      ) : (
        <div className="sessions-list">
          {sessions.map((s) => (
            <div key={s.id} className="session-card">
              <div className="session-card-top">
                <span className="session-mode">
                  {modeIcon(s.active_mode)} {s.active_mode || "Unknown"}
                </span>
                <span className="session-time">
                  {new Date(s.start_time).toLocaleString()}
                </span>
              </div>
              <div className="session-card-bottom">
                <span>Frames: {s.frames_processed}</span>
                <span>Duration: {formatDuration(s.start_time, s.end_time)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
