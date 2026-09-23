import { motion } from 'framer-motion'

export default function HUDOverlay({ children, title = 'SMART SYSTEM ACTIVE' }) {
  return (
    <div className="relative w-full h-full min-h-screen bg-black overflow-hidden">
      {/* Corner brackets */}
      <div className="absolute top-6 left-6 w-16 h-16 border-l-2 border-t-2 border-gold/40" />
      <div className="absolute top-6 right-6 w-16 h-16 border-r-2 border-t-2 border-gold/40" />
      <div className="absolute bottom-6 left-6 w-16 h-16 border-l-2 border-b-2 border-gold/40" />
      <div className="absolute bottom-6 right-6 w-16 h-16 border-r-2 border-b-2 border-gold/40" />

      {/* Top HUD bar */}
      <motion.div 
        className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-8 py-4"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-gold animate-pulse-glow" />
          <span className="text-gold/70 text-xs font-inter tracking-[0.3em] uppercase">{title}</span>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-white/30 text-xs font-mono tracking-wider">
            HALO VISION v2.0
          </div>
        </div>
      </motion.div>

      {/* Scan line animation */}
      <motion.div
        className="absolute left-0 right-0 h-px bg-gradient-to-r from-transparent via-gold/30 to-transparent z-10"
        animate={{ y: ['-100vh', '100vh'] }}
        transition={{ duration: 4, repeat: Infinity, ease: 'linear' }}
      />

      {/* Content */}
      <div className="relative z-10">
        {children}
      </div>
    </div>
  )
}
