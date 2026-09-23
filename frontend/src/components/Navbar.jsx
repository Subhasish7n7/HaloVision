import { useState, useRef, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { useAuth } from "../context/AuthContext"
import { LogOut, User, Settings, ShieldCheck } from "lucide-react"
import Particles from "../components/Particles"
import BackgroundEffects from "../components/BackgroundEffects"

export default function Navbar() {
  const navigate = useNavigate()
  const { token, user, logout } = useAuth()
  const [showDropdown, setShowDropdown] = useState(false)
  const dropdownRef = useRef(null)

  useEffect(() => {
    const handleClick = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener("mousedown", handleClick)
    return () => document.removeEventListener("mousedown", handleClick)
  }, [])

  const handleLogout = () => {
    logout()
    setShowDropdown(false)
    navigate("/")
  }

  return (
    <header className="fixed top-0 left-0 right-0 z-50 backdrop-blur-xl bg-black/30 border-b border-white/5">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <BackgroundEffects />
        <Particles />

        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-3"
        >
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center">
            <span className="text-black font-bold text-lg">H</span>
          </div>
          <span className="text-white font-poppins font-semibold text-lg">
            Halo Vision
          </span>
        </button>

        <nav className="hidden lg:flex items-center gap-8">
          <button
            onClick={() => navigate("/home")}
            className="text-sm text-white/70 hover:text-gold transition-colors"
          >
            Home
          </button>

          <button
            onClick={() => navigate("/features/navigation")}
            className="text-sm text-white/70 hover:text-gold transition-colors"
          >
            Navigation
          </button>

          <button
            onClick={() => navigate("/features/search")}
            className="text-sm text-white/70 hover:text-gold transition-colors"
          >
            Detection
          </button>

          <button
            onClick={() => navigate("/features/voice")}
            className="text-sm text-white/70 hover:text-gold transition-colors"
          >
            Voice Smart
          </button>

          <button
            onClick={() => navigate("/about")}
            className="text-sm text-white/70 hover:text-gold transition-colors"
          >
            About
          </button>

          <button
            onClick={() => navigate("/mission")}
            className="text-sm text-white/70 hover:text-gold transition-colors"
          >
            Mission
          </button>

          <button
            onClick={() => navigate("/contact")}
            className="text-sm text-white/70 hover:text-gold transition-colors"
          >Contact</button>

        </nav>

        <div className="flex items-center gap-4" ref={dropdownRef}>
          {token && user ? (
            <div className="relative">
              <button
                onClick={() => setShowDropdown(!showDropdown)}
                className="flex items-center gap-2 px-4 py-2 rounded-full border border-white/10 hover:border-gold/30 transition-colors bg-white/5"
              >
                <div className="w-7 h-7 rounded-full bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center overflow-hidden">
                  {user.photo_url ? (
                    <img src={user.photo_url} alt="" className="w-full h-full object-cover" />
                  ) : (
                    <span className="text-black font-bold text-xs">
                      {user.name ? user.name.charAt(0).toUpperCase() : "U"}
                    </span>
                  )}
                </div>
                <span className="text-sm text-white/80">Profile</span>
              </button>

              {showDropdown && (
                <div className="absolute right-0 mt-2 w-56 rounded-2xl border border-white/10 bg-black/90 backdrop-blur-2xl overflow-hidden shadow-2xl">
                  <div className="px-4 py-3 border-b border-white/5">
                    <p className="text-sm text-white font-medium">{user.name}</p>
                    <p className="text-xs text-white/40">{user.email}</p>
                  </div>
                  <button
                    onClick={() => { setShowDropdown(false); navigate("/profile") }}
                    className="w-full flex items-center gap-3 px-4 py-3 text-sm text-white/70 hover:text-gold hover:bg-white/5 transition-colors"
                  >
                    <User size={16} />
                    My Profile
                  </button>
                  <button
                    onClick={() => { setShowDropdown(false); navigate("/profile?edit=true") }}
                    className="w-full flex items-center gap-3 px-4 py-3 text-sm text-white/70 hover:text-gold hover:bg-white/5 transition-colors"
                  >
                    <Settings size={16} />
                    Edit Profile
                  </button>
                  {["super_admin", "admin", "moderator", "support"].includes(user.role) && (
                    <button
                      onClick={() => { setShowDropdown(false); navigate("/admin") }}
                      className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gold hover:bg-gold/5 transition-colors"
                    >
                      <ShieldCheck size={16} />
                      Admin Console
                    </button>
                  )}
                  <div className="border-t border-white/5">
                    <button
                      onClick={handleLogout}
                      className="w-full flex items-center gap-3 px-4 py-3 text-sm text-red-400 hover:bg-red-400/5 transition-colors"
                    >
                      <LogOut size={16} />
                      Sign Out
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <>
              <button
                onClick={() => navigate("/login")}
                className="px-5 py-2 text-sm text-white/70 hover:text-white transition-colors"
              >
                Login
              </button>

              <button
                onClick={() => navigate("/register")}
                className="px-5 py-2 text-sm font-medium text-black bg-gradient-to-r from-gold-dark to-gold rounded-full hover:shadow-[0_0_30px_rgba(255,179,71,0.2)] transition-shadow"
              >
                Get Started
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
