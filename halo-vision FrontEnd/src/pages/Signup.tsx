import { useState } from "react";

export default function Signup() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleSignup = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/auth/signup", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name,
          email,
          password,
        }),
      });

      const data = await res.json();

      if (res.ok) {
        alert("Signup successful ✅");

        // 🔥 clear form after success
        setName("");
        setEmail("");
        setPassword("");
      } else {
        // ✅ FIXED (backend sends "detail")
        alert(data.detail || "Signup failed");
      }

    } catch (err) {
      console.error("❌ Signup error:", err);
      alert("Server not reachable");
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.box}>
        <h2 style={styles.title}>Sign Up</h2>

        <input
          type="text"
          placeholder="Full Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          style={styles.input}
        />

        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={styles.input}
        />

        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={styles.input}
        />

        <button style={styles.button} onClick={handleSignup}>
          Create Account
        </button>
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
    width: "350px",
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

  input: {
    width: "100%",
    padding: "12px",
    marginBottom: "15px",
    borderRadius: "8px",
    border: "1.5px solid cyan",
    background: "black",
    color: "cyan",
    outline: "none",
  },

  button: {
    width: "100%",
    padding: "12px",
    borderRadius: "25px",
    border: "none",
    background: "linear-gradient(135deg, cyan, #00ffff)",
    color: "black",
    fontWeight: "bold",
    cursor: "pointer",
  },
};