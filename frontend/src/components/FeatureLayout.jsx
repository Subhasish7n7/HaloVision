import { motion } from "framer-motion"

export default function FeatureLayout({ title, children }) {
  return (
    <div className="min-h-screen bg-black relative overflow-hidden">
      <div className="fixed inset-0 pointer-events-none z-0">
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,179,71,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(255,179,71,0.3) 1px, transparent 1px)",
            backgroundSize: "80px 80px",
          }}
        />
        <div className="scanline absolute inset-0" />
        <motion.div
          animate={{ scale: [1, 1.2, 1], opacity: [0.3, 0.5, 0.3] }}
          transition={{ duration: 8, repeat: Infinity, ease: "easeInOut" }}
          className="absolute top-1/4 right-1/4 w-72 h-72 rounded-full"
          style={{ background: "radial-gradient(circle, rgba(255,179,71,0.08) 0%, transparent 70%)" }}
        />
      </div>

      <div className="relative z-10">
        <div className="border-b border-white/5 bg-black/40 backdrop-blur-xl">
          <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center">
                <span className="text-black font-bold text-sm">H</span>
              </div>
              <span className="text-xs font-mono text-white/50 tracking-widest">HALO VISION v2.0</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              <span className="text-xs text-white/40">System Active</span>
            </div>
          </div>
        </div>

        <div className="max-w-7xl mx-auto px-4 py-8">
          <motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-lg font-mono tracking-[0.2em] text-gold/80 mb-8 text-center"
          >
            {title}
          </motion.h1>
          {children}
        </div>
      </div>
    </div>
  )
}
