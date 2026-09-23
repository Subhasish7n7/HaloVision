import { useState } from "react";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";
import GlassCard from "../components/GlassCard";
import Navbar from "../components/Navbar";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function Contact() {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    message: "",
  });

  const [status, setStatus] = useState("idle"); // idle | sending | success | error
  const [statusText, setStatusText] = useState("");

  const fadeUp = {
    initial: { opacity: 0, y: 30 },
    whileInView: { opacity: 1, y: 0 },
    viewport: { once: true },
    transition: { duration: 0.6 },
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setStatus("sending");
    setStatusText("");

    try {
      const res = await fetch(`${API_BASE}/api/contact`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });

      const data = await res.json();

      if (res.ok) {
        setStatus("success");
        setStatusText("Message sent successfully!");
        setFormData({ name: "", email: "", message: "" });
      } else {
        setStatus("error");
        setStatusText(data.detail || "Failed to send message");
      }
    } catch {
      setStatus("error");
      setStatusText("Server not reachable. Please try again later.");
    }
  };

  return (
    <div className="min-h-screen bg-black text-white py-24">
        <Navbar />
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">

        <motion.div {...fadeUp} className="text-center mb-12">
          <span className="inline-block px-3 py-1 text-xs font-mono tracking-wider text-gold border border-gold/20 rounded-full mb-4">
            Get in Touch
          </span>

          <h1 className="font-poppins text-3xl md:text-5xl font-bold mb-4">
            Let's{" "}
            <span className="bg-gradient-to-r from-gold to-gold-light bg-clip-text text-transparent">
              Connect
            </span>
          </h1>

          <p className="text-white/50">
            Interested in Halo Vision? Reach out to learn more about our technology.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
        >
          <GlassCard className="p-8">

            <form className="space-y-6" onSubmit={handleSubmit}>

              <div>
                <label className="block text-sm text-white/60 mb-2">
                  Name
                </label>

                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) =>
                    setFormData({ ...formData, name: e.target.value })
                  }
                  className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-gold/50"
                  placeholder="Your Name"
                  required
                />
              </div>

              <div>
                <label className="block text-sm text-white/60 mb-2">
                  Email
                </label>

                <input
                  type="email"
                  value={formData.email}
                  onChange={(e) =>
                    setFormData({ ...formData, email: e.target.value })
                  }
                  className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-gold/50"
                  placeholder="your@email.com"
                  required
                />
              </div>

              <div>
                <label className="block text-sm text-white/60 mb-2">
                  Message
                </label>

                <textarea
                  rows={5}
                  value={formData.message}
                  onChange={(e) =>
                    setFormData({ ...formData, message: e.target.value })
                  }
                  className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-gold/50 resize-none"
                  placeholder="Write your message..."
                  required
                />
              </div>

              {status === "success" && (
                <p className="text-green-400 text-center">
                  {statusText}
                </p>
              )}

              {status === "error" && (
                <p className="text-red-400 text-center">
                  {statusText}
                </p>
              )}

              <button
                type="submit"
                disabled={status === "sending"}
                className="w-full py-3 rounded-full bg-gradient-to-r from-gold-dark to-gold text-black font-semibold disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {status === "sending" ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Sending...
                  </>
                ) : (
                  "Send Message"
                )}
              </button>

            </form>

          </GlassCard>
        </motion.div>
      </div>
    </div>
  );
}
