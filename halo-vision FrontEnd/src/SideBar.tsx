export const Sidebar = ({ setMode }: any) => {
  const items = [
    { icon: "", label: "Helo", mode: "camera" },
    { icon: "🎤", label: "Voice", mode: "voice" },
    { icon: "🧠", label: "AI", mode: "ai" },
    { icon: "🔎", label: "Search", mode: "search" },
    { icon: "🔒", label: "Secure", mode: "secure" },
  ];

  return (
    <div
      style={{
        width: "90px",
        borderRight: "1px solid rgba(0,255,255,0.2)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        paddingTop: "20px",
        gap: "25px",
      }}
    >
      {items.map((item, i) => (
        <div
          key={i}
          onClick={() => setMode(item.mode)}
          style={{
            cursor: "pointer",
            textAlign: "center",
            color: "cyan",
          }}
        >
          <div style={{ fontSize: "22px" }}>{item.icon}</div>
          <div style={{ fontSize: "10px", marginTop: "4px" }}>
            {item.label}
          </div>
        </div>
      ))}
    </div>
  );
};