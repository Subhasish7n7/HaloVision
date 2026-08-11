import { useState, useEffect } from "react";
import "./search-queries.css";

type SearchQuery = {
  id: number;
  query_text: string;
  found: number | null;
  timestamp: string;
};

export default function SearchQueries() {
  const [queries, setQueries] = useState<SearchQuery[]>([]);

  useEffect(() => {
    const token = localStorage.getItem("token");
    fetch("http://localhost:8000/api/search-queries", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.json())
      .then((data) => setQueries(data))
      .catch(() => {});
  }, []);

  return (
    <div className="sq-container">
      <div className="sq-header">
        <h2>Search History</h2>
        <p>Objects you've searched for</p>
      </div>

      {queries.length === 0 ? (
        <p className="sq-empty">No searches recorded</p>
      ) : (
        <div className="sq-list">
          {queries.map((q) => (
            <div key={q.id} className="sq-card">
              <div className="sq-card-top">
                <span className="sq-query">"{q.query_text}"</span>
                <span className="sq-found">
                  {q.found === 1 ? "✅ Found" : "❌ Not found"}
                </span>
              </div>
              <div className="sq-card-bottom">
                <span className="sq-time">
                  {new Date(q.timestamp).toLocaleString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
