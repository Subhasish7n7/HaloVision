import "./Auth.css";

export default function Login() {
  return (
    <div className="auth-container">

      <div className="auth-box">
        <h2>Login</h2>

        <input type="email" placeholder="Email" />
        <input type="password" placeholder="Password" />

        <button className="auth-btn">Login</button>
      </div>

    </div>
  );
}