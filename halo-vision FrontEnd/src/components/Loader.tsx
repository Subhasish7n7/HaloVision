// components/Loader.tsx
import "./loader.css";

export default function Loader() {
  return (
    <div className="loader-container">
      <div className="halo-loader">
        <div className="dot"></div>
        <div className="ring"></div>
      </div>
      <p className="loading-text">Halo Vision</p>
    </div>
  );
}