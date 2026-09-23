import { useCallback, useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { motion } from "framer-motion"
import {
  ArrowRight,
  Activity,
  Radar,
  ShieldAlert,
  Database,
  Search as SearchIcon,
  RefreshCw,
} from "lucide-react"
import Navbar from "../components/Navbar"
import Footer from "../components/Footer"
import BackgroundEffects from "../components/BackgroundEffects"
import GlassCard from "../components/GlassCard"
import { useAuth } from "../context/AuthContext"
import { features } from "../data/features"

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"

const fadeUp = {
  initial: { opacity: 0, y: 40 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-60px" },
  transition: { duration: 0.6 },
}

export default function HomePage() {
  const navigate = useNavigate()
  const { token, user, checking } = useAuth()

  const [stats, setStats] = useState(null)
  const [recent, setRecent] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const loadDashboard = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError("")

    const headers = { Authorization: `Bearer ${token}` }

    try {
      const [statsData, dets, sesses, alerts, queries] = await Promise.all([
        fetch(`${API_BASE}/api/dashboard/stats`, { headers }).then((r) => {
          if (!r.ok) throw new Error("Failed to load dashboard stats")
          return r.json()
        }),
        fetch(`${API_BASE}/api/detections`, { headers }).then((r) => (r.ok ? r.json() : [])),
        fetch(`${API_BASE}/api/sessions`, { headers }).then((r) => (r.ok ? r.json() : [])),
        fetch(`${API_BASE}/api/alerts`, { headers }).then((r) => (r.ok ? r.json() : [])),
        fetch(`${API_BASE}/api/search-queries`, { headers }).then((r) => (r.ok ? r.json() : [])),
      ])

      setStats({
        detections: statsData.detections,
        sessions: statsData.sessions,
        alerts: statsData.alerts,
        searches: statsData.searches,
      })

      const items = [
        ...dets.map((d) => ({ kind: "detection", label: d.label || "object", ts: d.timestamp })),
        ...sesses.map((s) => ({ kind: "session", label: s.active_mode || "session", ts: s.start_time })),
        ...alerts.map((a) => ({ kind: "alert", label: a.message || a.type, ts: a.timestamp })),
        ...queries.map((q) => ({ kind: "search", label: q.query_text, ts: q.timestamp })),
      ].sort((a, b) => new Date(b.ts || 0) - new Date(a.ts || 0))

      setRecent(items.slice(0, 8))
    } catch (e) {
      setError("Could not reach the database. Make sure the backend is running.")
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    // Wait for auth validation on boot so we never fire the dashboard
    // requests with a stale/expired token (which would 401 in the console).
    if (checking) return
    loadDashboard()
  }, [checking, loadDashboard])

  const statCards = stats
    ? [
        { label: "DETECTIONS IN DB", value: stats.detections, icon: Radar, color: "text-cyan-400" },
        { label: "SESSION", value: stats.sessions, icon: Activity, color: "text-gold" },
        { label: "ALERTS IN DB", value: stats.alerts, icon: ShieldAlert, color: "text-red-400" },
        { label: "SMART SEARCHES", value: stats.searches, icon: SearchIcon, color: "text-emerald-400" },
      ]
    : []

  return (
    <div className="min-h-screen bg-black">
      <Navbar />
      <BackgroundEffects />

      {/* DASHBOARD HERO */}
      <section className="relative min-h-screen flex items-center pt-20 pb-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full">
          <motion.div
            initial={{ opacity: 0, x: -40 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8 }}
            className="mb-10"
          >
            <span className="inline-block px-3 py-1 text-xs font-mono tracking-wider text-gold border border-gold/20 rounded-full mb-6">
              {user ? `Welcome back, ${user.name || "there"}` : "Halo Vision"}
            </span>

            <h1 className="font-poppins text-4xl md:text-5xl font-bold leading-tight mb-4">
              <span className="bg-gradient-to-r from-gold to-gold-light bg-clip-text text-transparent">
                Smart Vision
              </span>
            </h1>

            <p className="text-white/50 text-lg leading-relaxed max-w-xl">
              Realtime smart scene understanding, spatial navigation, and intelligent voice guidance. Your data below is
              loaded straight from the live database.
            </p>

            <div className="flex flex-wrap gap-4 mt-8">
              <button
                onClick={() => navigate("/features/navigation")}
                className="px-6 py-3 text-sm font-medium text-black bg-gradient-to-r from-gold-dark to-gold rounded-full hover:shadow-[0_0_30px_rgba(255,179,71,0.25)] transition-all hover:-translate-y-0.5 active:scale-95 flex items-center gap-2"
              >
                Launch Live Vision <ArrowRight size={16} />
              </button>

              <button
                onClick={loadDashboard}
                className="px-6 py-3 text-sm font-medium text-white/80 border border-white/20 rounded-full hover:border-gold/40 hover:text-gold transition-colors flex items-center gap-2"
              >
                <RefreshCw size={15} className={loading ? "animate-spin" : ""} /> Refresh
              </button>
            </div>
          </motion.div>

          {/* REAL DATABASE STATS */}
          {!token ? (
            <motion.div {...fadeUp} className="rounded-3xl border border-white/10 bg-white/[0.03] p-8 text-center max-w-xl">
              <Database size={30} className="text-gold mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-white mb-2">Sign in to view your data</h2>
              <p className="text-white/40 text-sm mb-6">Your saved sessions, detections and searches will appear here.</p>
              <div className="flex gap-3 justify-center">
                <button onClick={() => navigate("/login")} className="px-5 py-2.5 text-sm font-medium text-black bg-gradient-to-r from-gold-dark to-gold rounded-full">
                  Login
                </button>
                <button onClick={() => navigate("/register")} className="px-5 py-2.5 text-sm text-white/80 border border-white/20 rounded-full hover:border-gold/40">
                  Create Account
                </button>
              </div>
            </motion.div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-12">
              {(loading && !stats
                ? [
                    { label: "DETECTIONS IN DB", value: "\u2014", icon: Radar, color: "text-cyan-400" },
                    { label: "SESSION", value: "\u2014", icon: Activity, color: "text-gold" },
                    { label: "ALERTS IN DB", value: "\u2014", icon: ShieldAlert, color: "text-red-400" },
                    { label: "SMART SEARCHES", value: "\u2014", icon: SearchIcon, color: "text-emerald-400" },
                  ]
                : statCards
              ).map((card, i) => (
                <motion.div key={card.label} {...fadeUp} transition={{ delay: i * 0.08, duration: 0.5 }}>
                  <div className="rounded-2xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-5">
                    <card.icon size={20} className={card.color + " mb-3"} />
                    <div className={`text-3xl font-bold font-poppins ${card.color}`}>{card.value}</div>
                    <div className="text-[10px] font-mono tracking-widest text-white/40 mt-1">{card.label}</div>
                  </div>
                </motion.div>
              ))}
            </div>
          )}

          {error && <p className="text-sm text-red-400 mb-8 flex items-center gap-2"><ShieldAlert size={15} /> {error}</p>}

          {/* LIVE ACTIVITY FEED (real DB records) */}
          {token && recent.length > 0 && (
            <motion.div {...fadeUp} className="mb-14">
              <div className="flex items-center gap-2 mb-4">
                <Activity size={16} className="text-gold" />
                <h2 className="font-poppins font-semibold text-lg text-white">Latest Activity</h2>
              </div>
              <div className="rounded-3xl border border-white/10 bg-white/[0.02] backdrop-blur-xl overflow-hidden">
                {recent.map((item, i) => (
                  <div key={i} className="flex items-center gap-4 px-5 py-3 border-b border-white/5 last:border-0">
                    <span className="text-xs font-mono text-white/30 w-24 shrink-0">
                      {item.ts ? new Date(item.ts).toLocaleString([], { dateStyle: "short", timeStyle: "medium" }) : "—"}
                    </span>
                    {item.kind === "detection" && (
                      <span className="px-2 py-0.5 text-[10px] font-mono rounded-full text-cyan-300 bg-cyan-400/10 border border-cyan-400/20">DETECTED</span>
                    )}
                    {item.kind === "session" && (
                      <span className="px-2 py-0.5 text-[10px] font-mono rounded-full text-gold bg-gold/10 border border-gold/20">SESSION</span>
                    )}
                    {item.kind === "alert" && (
                      <span className="px-2 py-0.5 text-[10px] font-mono rounded-full text-red-300 bg-red-400/10 border border-red-400/20">ALERT</span>
                    )}
                    {item.kind === "search" && (
                      <span className="px-2 py-0.5 text-[10px] font-mono rounded-full text-emerald-300 bg-emerald-400/10 border border-emerald-400/20">SEARCH</span>
                    )}
                    <span className="text-sm text-white/80 truncate">{item.label}</span>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </div>
      </section>

      {/* REAL FEATURES GRID */}
      <section className="pb-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div {...fadeUp} className="text-center mb-12">
            <span className="inline-block px-3 py-1 text-xs font-mono tracking-wider text-gold border border-gold/20 rounded-full mb-4">
              Live Modes
            </span>
            <h2 className="font-poppins text-3xl md:text-4xl font-bold">
              <span className="bg-gradient-to-r from-gold to-gold-light bg-clip-text text-transparent">Capabilities</span>
            </h2>
            <p className="text-white/50 max-w-2xl mx-auto mt-3">
              Five real smart modules solving real assistive vision problems — nothing simulated.
            </p>
          </motion.div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((feature, i) => (
              <motion.div key={feature.title} {...fadeUp} transition={{ delay: i * 0.08, duration: 0.5 }}>
                <motion.button
                  whileHover={{ y: -8, scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => navigate(feature.link)}
                  className="text-left h-full w-full group"
                >
                  <GlassCard className="h-full flex flex-col cursor-pointer border border-white/5 hover:border-gold/20 transition-all duration-500 relative overflow-hidden">
                    <div
                      className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500"
                      style={{ background: `radial-gradient(circle at top right, ${feature.color}20 0%, transparent 60%)` }}
                    />
                    <div className="relative z-10 w-14 h-14 rounded-2xl flex items-center justify-center mb-5 border border-white/5" style={{ background: `${feature.color}15` }}>
                      <feature.icon size={26} style={{ color: feature.color }} />
                    </div>
                    <h3 className="relative z-10 font-poppins font-semibold text-xl text-white mb-3">{feature.title}</h3>
                    <p className="relative z-10 text-white/50 text-sm leading-relaxed flex-1">{feature.description}</p>
                    <div className="relative z-10 mt-6 flex items-center gap-2 text-gold text-sm font-medium">
                      Open Mode <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                    </div>
                  </GlassCard>
                </motion.button>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      <Footer />
    </div>
  )
}