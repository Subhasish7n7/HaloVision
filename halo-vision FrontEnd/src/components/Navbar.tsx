import { Link } from "react-router-dom";
import "./navbar.css";
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap/dist/js/bootstrap.bundle.min.js';

export default function Navbar() {
  return (
    <nav className="navbar navbar-expand-lg halo-navbar">
      <div className="container-fluid">

        {/* LOGO */}
        <Link className="navbar-brand halo-logo" to="/">
          Halo Vision
        </Link>

        {/* MOBILE TOGGLE */}
        <button
          className="navbar-toggler"
          type="button"
          data-bs-toggle="collapse"
          data-bs-target="#navbarContent"
        >
          <span className="navbar-toggler-icon"></span>
        </button>

        {/* CONTENT */}
        <div className="collapse navbar-collapse" id="navbarContent">

          {/* CENTER LINKS */}
          <ul className="navbar-nav mx-auto">
            <li className="nav-item">
              <Link className="nav-link halo-link" to="/">Home</Link>
            </li>
            <li className="nav-item">
              <Link className="nav-link halo-link" to="/about">About</Link>
            </li>
            <li className="nav-item">
              <Link className="nav-link halo-link" to="/why">Why Choose Us</Link>
            </li>
          </ul>

          {/* RIGHT BUTTONS */}
          <div className="d-flex gap-2">
            <Link to="/login" className="btn halo-btn-outline">
              Login
            </Link>
            <Link to="/signup" className="btn halo-btn">
              Sign Up
            </Link>
          </div>

        </div>
      </div>
    </nav>
  );
}