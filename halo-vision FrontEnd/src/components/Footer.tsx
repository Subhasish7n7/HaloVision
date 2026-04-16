// components/Footer.tsx
import "./footer.css";

export default function Footer() {
  return (
    <footer className="halo-footer">
      <div className="footer-content">

        <div>
          <h4>Halo Vision</h4>
          <p>AI-powered assistive vision for a smarter world.</p>
        </div>

        <div>
          <h5>Links</h5>
          <p>Home</p>
          <p>About</p>
          <p>Why Choose Us</p>
        </div>

        <div>
          <h5>Legal</h5>
          <p>Privacy Policy</p>
          <p>Terms of Service</p>
        </div>

      </div>

      <p className="copyright">
        © 2026 Halo Vision. All rights reserved.
      </p>
    </footer>
  );
}