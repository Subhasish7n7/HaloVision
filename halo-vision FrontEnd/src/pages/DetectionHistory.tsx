import { useState, useEffect } from "react";
import "./detection-history.css";

type Detection = {
  id: number;
  label: string;
  confidence: number;
  distance: number | null;
  threat_level: number;
  timestamp: string;
};

export default function DetectionHistory() {
  const [detections, setDetections] = useState<Detection[]>([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("token");
    fetch("http://localhost:8000/api/detections", {
      headers: {
        Authorization: `Bearer ${token}`,
      },
    })
      .then((res) => res.json())
      .then((data) => setDetections(data))
      .catch(() => {});
  }, []);

  const filtered = detections.filter((d) =>
    d.label.toLowerCase().includes(search.toLowerCase())
  );

  const getThreatColor = (level: number) => {
    if (level >= 3) return "red";
    if (level >= 2) return "orange";
    if (level >= 1) return "yellow";
    return "cyan";
  };

  return (
    <div className="history-container">
      <div className="history-header">
        <h2>Detection History</h2>
        <p>Past detected objects and threats</p>
      </div>

      <div className="history-search">
        <input
          className="history-input"
          placeholder="Filter by object name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {filtered.length === 0 ? (
        <p className="history-empty">No detections found</p>
      ) : (
        <div className="history-list">
          {filtered.map((d) => (
            <div key={d.id} className="history-card">
              <div className="history-card-top">
                <span
                  className="history-label"
                  style={{
                    borderColor: getThreatColor(d.threat_level),
                    color: getThreatColor(d.threat_level),
                  }}
                >
                  {d.label}
                </span>
                <span className="history-time">
                  {new Date(d.timestamp).toLocaleString()}
                </span>
              </div>
              <div className="history-card-bottom">
                <span>Conf: {(d.confidence * 100).toFixed(1)}%</span>
                <span>
                  Dist: {d.distance ? `${d.distance.toFixed(2)}m` : "N/A"}
                </span>
                <span
                  style={{ color: getThreatColor(d.threat_level) }}
                >
                  Threat: Lv{d.threat_level}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
