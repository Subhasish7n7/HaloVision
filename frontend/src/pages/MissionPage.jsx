import { motion } from "framer-motion"
import { Users, Cpu, Globe, DollarSign } from "lucide-react"
import Navbar from "../components/Navbar"
import Footer from "../components/Footer"
import BackgroundEffects from "../components/BackgroundEffects"
import ParticleField from "../components/Particles"

const fadeUp = {
  initial: { opacity: 0, y: 40 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-100px" },
  transition: { duration: 0.6 },
}

export default function MissionPage() {
  return (
    <div className="min-h-screen bg-black relative overflow-hidden">
      <BackgroundEffects />
      <ParticleField />

      <Navbar />

      <section className="pt-32 pb-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <motion.div {...fadeUp}>
              <span className="inline-block px-3 py-1 text-xs font-mono tracking-wider text-gold border border-gold/20 rounded-full mb-4">
                Our Mission
              </span>
              <h2 className="font-poppins text-3xl md:text-5xl font-bold mb-6">
                Technology That{" "}
                <span className="bg-gradient-to-r from-gold to-gold-light bg-clip-text text-transparent">
                  Sees for You
                </span>
              </h2>
              <p className="text-white/50 leading-relaxed mb-8">
                Over 2.2 billion people worldwide live with vision impairment. Halo Vision pairs smart
                computer-vision models with advanced sensor arrays and spatial computing to restore
                independence, safety, and confidence — turning what was invisible into something you
                can feel, hear, and trust.
              </p>
              <div className="grid grid-cols-2 gap-6">
                {[
                  { value: "2.2B+", label: "People with Vision Impairment", icon: Users },
                  { value: "28", label: "Machine Learning Models", icon: Cpu },
                  { value: "47", label: "Countries Targeted", icon: Globe },
                  { value: "$4.2M", label: "Seed Funding Raised", icon: DollarSign },
                ].map((s) => (
                  <div key={s.label} className="flex items-start gap-3">
                    <s.icon size={18} className="text-gold/60 mt-1 shrink-0" />
                    <div>
                      <div className="font-poppins font-bold text-xl text-white">{s.value}</div>
                      <div className="text-xs text-white/40">{s.label}</div>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, x: 40 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              className="relative"
            >
              <div className="aspect-square rounded-2xl border border-white/5 bg-white/[0.02] backdrop-blur-xl overflow-hidden">
                <img
                  src="https://media.base44.com/images/public/6a159474812a50f1a5df7ebc/822634a72_generated_f982f60f.png"
                  alt="Halo Vision Smart Glasses"
                  className="w-full h-full object-cover opacity-80"
                />
              </div>
            </motion.div>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  )
}
