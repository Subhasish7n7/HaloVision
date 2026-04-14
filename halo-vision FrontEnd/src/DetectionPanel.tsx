type Props = {
  detections: any[];
};

export const DetectionPanel = ({ detections }: Props) => {
  const getColor = (label: string) => {
    if (label.toLowerCase().includes("person")) return "red";
    return "cyan";
  };

  return (
    <div
      style={{
        width: "300px",
        borderLeft: "1px solid rgba(0,255,255,0.2)",
        padding: "15px",
      }}
    >
      <h3 style={{ color: "white", marginBottom: "10px" }}>
        Detection Panel
      </h3>

      {detections.length === 0 && (
        <p style={{ color: "gray" }}>No data yet</p>
      )}

      {detections.map((d, i) => (
        <div
          key={i}
          style={{
            border: `1px solid ${getColor(d.label)}`,
            padding: "10px",
            marginBottom: "10px",
            borderRadius: "8px",
            color: getColor(d.label),
          }}
        >
          <strong>{d.label}</strong>
        </div>
      ))}
    </div>
  );
};