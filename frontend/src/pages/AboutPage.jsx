import { motion } from "framer-motion"
import { useNavigate } from "react-router-dom"

import Navbar from "../components/Navbar"
import Footer from "../components/Footer"
import BackgroundEffects from "../components/BackgroundEffects"
import ParticleField from "../components/Particles"

export default function About() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-black relative overflow-hidden">
      <Navbar />
      <BackgroundEffects />
      <ParticleField />

      <section className="relative pt-20 pb-24">
        <div className="max-w-7xl mx-auto px-6">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            {/* LEFT */}
            <motion.div
              initial={{
                opacity: 0,
                x: -40,
              }}

              animate={{
                opacity: 1,
                x: 0,
              }}

              transition={{
                duration: 0.8,
              }}
            >
              <span className="inline-block px-3 py-1 text-xs font-mono tracking-wider text-gold border border-gold/20 rounded-full mb-4">
                About Halo Vision
              </span>

              <h1 className="font-poppins text-5xl md:text-6xl font-bold text-white leading-tight mb-6">
                Technology That{" "}

                <span className="bg-gradient-to-r from-gold to-gold-light bg-clip-text text-transparent">
                  Sees Beyond
                </span>
              </h1>

              <p className="text-white/50 text-lg leading-relaxed mb-6">
                Halo Vision is a smart assistive system designed
                to enhance human perception through real-time
                object detection, intelligent scene analysis,
                and voice interaction.
              </p>

              <p className="text-white/50 text-lg leading-relaxed mb-8">
                Our mission is to create a futuristic wearable
                ecosystem that improves navigation, accessibility,
                safety, and independence using advanced machine-learning
                technologies.
              </p>

              <button
                onClick={() => navigate("/mission")}
                className="px-7 py-3 text-sm font-medium text-black bg-gradient-to-r from-gold-dark to-gold rounded-full hover:shadow-[0_0_30px_rgba(255,179,71,0.15)] transition-shadow"
              >
                Read More
              </button>
            </motion.div>

            {/* RIGHT */}
            <motion.div
              initial={{
                opacity: 0,
                x: 40,
              }}

              animate={{
                opacity: 1,
                x: 0,
              }}

              transition={{
                duration: 0.8,
                delay: 0.2,
              }}

              className="space-y-6"
            >
              {/* CARD 1 */}
              <div className="p-6 rounded-3xl border border-gold/10 bg-white/[0.03] backdrop-blur-xl hover:border-gold/20 transition-all duration-300">
                <div className="w-14 h-14 rounded-2xl bg-gold/10 border border-gold/10 flex items-center justify-center text-2xl mb-5">
                  ⚡
                </div>

                <h3 className="font-poppins text-xl font-semibold text-white mb-3">
                  Real-Time Detection
                </h3>

                <p className="text-white/50 leading-relaxed">
                  Detect objects instantly and provide immediate
                  smart feedback based on live camera input.
                </p>
              </div>

              {/* CARD 2 */}
              <div className="p-6 rounded-3xl border border-gold/10 bg-white/[0.03] backdrop-blur-xl hover:border-gold/20 transition-all duration-300">
                <div className="w-14 h-14 rounded-2xl bg-gold/10 border border-gold/10 flex items-center justify-center text-2xl mb-5">
                  🎤
                </div>

                <h3 className="font-poppins text-xl font-semibold text-white mb-3">
                  Voice Interaction
                </h3>

                <p className="text-white/50 leading-relaxed">
                  Receive intelligent audio feedback and interact
                  with the system using smart voice responses.
                </p>
              </div>

              {/* CARD 3 */}
              <div className="p-6 rounded-3xl border border-gold/10 bg-white/[0.03] backdrop-blur-xl hover:border-gold/20 transition-all duration-300">
                <div className="w-14 h-14 rounded-2xl bg-gold/10 border border-gold/10 flex items-center justify-center text-2xl mb-5">
                  🔧
                </div>

                <h3 className="font-poppins text-xl font-semibold text-white mb-3">
                  Efficient Architecture
                </h3>

                <p className="text-white/50 leading-relaxed">
                  Built using a lightweight responsive system
                  architecture for smooth and efficient machine
                  learning.
                </p>
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  )
}