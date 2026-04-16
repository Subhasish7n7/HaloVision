type Props = {
  label: string;
  message?: string;
  threat: 0 | 1 | 2 | 3;
};

export default function DetectionCard({ label, message, threat }: Props) {

  // 🎨 COLOR FROM BACKEND THREAT
  const getColor = () => {
    switch (threat) {
      case 0:
      case 1:
        return "cyan";
      case 2:
        return "yellow";
      case 3:
        return "red";
      default:
        return "cyan";
    }
  };

  // 🎯 ICON (ONLY VISUAL)
  const getIcon = () => {
    const name = label.toLowerCase();

    if (name.includes("person")) return "👤";
    if (name.includes("car") || name.includes("bike") || name.includes("truck")) return "🚗";
    if (name.includes("chair")) return "🪑";

    return "📦";
  };

  const color = getColor();

  return (
    <div className={`detect-card ${threat === 3 ? "danger" : ""}`}>

      {/* LEFT BAR */}
      <div
        className="detect-bar"
        style={{ backgroundColor: color }}
      />

      {/* CONTENT */}
      <div className="detect-content">
        <div className="detect-title" style={{ color }}>
          {getIcon()} {label}
        </div>

        <div className="detect-message" style={{ color }}>
          {message || "Detected"}
        </div>
      </div>

    </div>
  );
}