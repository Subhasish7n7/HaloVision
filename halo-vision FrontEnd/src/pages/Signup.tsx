import { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function Signup() {
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // ✅ REGEX
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const passwordRegex = /^[A-Za-z0-9]{6,}$/;

  const handleSignup = async () => {
    setError("");
    setSuccess("");

    // =========================
    // VALIDATION
    // =========================
    if (!name.trim()) {
      setError("Full name is required");
      return;
    }

    if (!emailRegex.test(email)) {
      setError("Invalid email format");
      return;
    }

    if (!passwordRegex.test(password)) {
      setError("Password must be at least 6 characters (letters & numbers only)");
      return;
    }

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
        setSuccess("Signup successful ✅ Redirecting...");

        setName("");
        setEmail("");
        setPassword("");

        // 🔥 redirect after short delay (better UX)
        setTimeout(() => {
          navigate("/");
        }, 1500);

      } else {
        setError(data.detail || "Signup failed");
      }

    } catch (err) {
      console.error("❌ Signup error:", err);
      setError("Server not reachable");
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

        {/* 🔥 MESSAGE AREA */}
        {error && <p style={styles.error}>{error}</p>}
        {success && <p style={styles.success}>{success}</p>}
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

  error: {
    color: "red",
    marginTop: "12px",
    fontSize: "14px",
  },

  success: {
    color: "lightgreen",
    marginTop: "12px",
    fontSize: "14px",
  },
};