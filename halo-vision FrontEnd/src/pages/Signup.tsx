import "./Auth.css";

export default function Signup() {
  return (
    <div className="auth-container">

      <div className="auth-box">
        <h2>Sign Up</h2>

        <input type="text" placeholder="Full Name" />
        <input type="email" placeholder="Email" />
        <input type="password" placeholder="Password" />

        <button className="auth-btn">Create Account</button>
      </div>

    </div>
  );
}