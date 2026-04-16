import "./About.css";

export default function About() {
  return (
    <div className="about-container">

      <div className="about-left">
        <h2 className="about-title">About Halo Vision</h2>

        <p className="about-text">
          Halo Vision is an assistive system designed to enhance
          human perception through real-time object detection,
          scene understanding, and voice interaction.
        </p>

        <p className="about-text">
          Our goal is to create a system that is simple, responsive,
          and helpful in everyday situations by combining visual input
          with intelligent processing.
        </p>

        <button className="about-btn">Read More</button>
      </div>

      <div className="about-right">
        <div className="feature-box">
          <h4>⚡ Real-Time Detection</h4>
          <p>
            Detect objects instantly and provide immediate feedback
            based on live camera input.
          </p>
        </div>

        <div className="feature-box">
          <h4>🎤 Voice Interaction</h4>
          <p>
            Receive audio feedback and interact with the system
            using simple voice-based responses.
          </p>
        </div>

        <div className="feature-box">
          <h4>🔧 Efficient System Design</h4>
          <p>
            Built with a lightweight and responsive architecture
            for smooth real-time performance.
          </p>
        </div>
      </div>

    </div>
  );
}