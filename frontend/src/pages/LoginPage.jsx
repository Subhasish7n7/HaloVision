import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Eye, EyeOff } from "lucide-react"
import { motion } from "framer-motion"
import { useAuth } from "../context/AuthContext"
import BackgroundEffects from "../components/BackgroundEffects"
import ParticleField from "../components/Particles"

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"

export default function LoginPage() {
  const navigate = useNavigate()
  const { login, savedEmail } = useAuth()

  const [showPassword, setShowPassword] = useState(false)
  const [email, setEmail] = useState(savedEmail || "")
  const [password, setPassword] = useState("")
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const handleLogin = async (e) => {
    e.preventDefault()
    setError("")
    setLoading(true)

    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      })

      const data = await res.json()

      if (res.ok) {
        login(data.token, data.user, remember)
        navigate("/home", { replace: true })
      } else {
        setError(data.detail || "Invalid credentials")
      }
    } catch (err) {
      setError("Server not reachable")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-black flex relative overflow-hidden">
      <BackgroundEffects />
      <ParticleField />

      <div className="hidden lg:flex lg:w-1/2 relative items-center justify-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.8 }}
          className="relative"
        >
          <div className="w-80 h-80 rounded-full border border-gold/10" />
          <div className="absolute inset-4 rounded-full border border-dashed border-gold/5" />
          <img
            src="https://media.base44.com/images/public/6a159474812a50f1a5df7ebc/822634a72_generated_f982f60f.png"
            alt="Halo Vision Smart Glasses"
            className="absolute inset-0 w-full h-full object-contain p-12 drop-shadow-[0_0_40px_rgba(255,179,71,0.2)]"
          />
          <p className="absolute -bottom-12 left-1/2 -translate-x-1/2 text-sm text-white/40 text-center whitespace-nowrap">
            The future of assistive vision technology
          </p>
        </motion.div>
      </div>

      <div className="flex-1 flex items-center justify-center p-4">
        <motion.div
          initial={{ opacity: 0, x: 40 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="w-full max-w-md"
        >
          <div className="text-center mb-8">
            <button
              onClick={() => navigate("/")}
              className="inline-flex items-center gap-2 mb-6"
            >
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center">
                <span className="text-black font-bold text-lg">H</span>
              </div>
            </button>
            <h1 className="font-poppins text-3xl font-bold text-white mb-2">
              Welcome back
            </h1>
            <p className="text-white/50 text-sm">
              Sign in to access your Halo Vision dashboard
            </p>
          </div>

          <form className="space-y-5" onSubmit={handleLogin}>
            <div>
              <label className="block text-sm text-white/60 mb-2">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-gold/50 transition-colors"
                placeholder="you@example.com"
                required
              />
            </div>

            <div>
              <label className="block text-sm text-white/60 mb-2">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-gold/50 transition-colors pr-10"
                  placeholder="••••••••"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white/60"
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                  className="accent-gold rounded"
                />
                <span className="text-sm text-white/50">Remember me</span>
              </label>
            </div>

            {error && (
              <p className="text-red-400 text-sm text-center">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 text-sm font-medium text-black bg-gradient-to-r from-gold-dark to-gold rounded-full hover:shadow-[0_0_30px_rgba(255,179,71,0.15)] transition-shadow disabled:opacity-50"
            >
              {loading ? "Signing In..." : "Sign In"}
            </button>
          </form>

          <p className="text-center mt-6 text-sm text-white/40">
            Don't have an account?{" "}
            <button
              onClick={() => navigate("/register")}
              className="text-gold hover:text-gold-light transition-colors"
            >
              Sign Up
            </button>
          </p>
        </motion.div>
      </div>
    </div>
  )
}
