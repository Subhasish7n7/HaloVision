import { useState, useEffect, useRef } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import { motion } from "framer-motion"
import { ArrowLeft, Camera, Save, Loader2, Lock, Eye, EyeOff, Phone, MapPin, Mail, User } from "lucide-react"
import { useAuth } from "../context/AuthContext"
import BackgroundEffects from "../components/BackgroundEffects"
import ParticleField from "../components/Particles"

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"

export default function ProfilePage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { token, user, updateUser, logout } = useAuth()
  const editRef = useRef(null)
  const [name, setName] = useState(user?.name || "")
  const [phone, setPhone] = useState(user?.phone || "")
  const [address, setAddress] = useState(user?.address || "")
  const [photoUrl, setPhotoUrl] = useState(user?.photo_url || "")
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState("")
  const [messageType, setMessageType] = useState("")

  const [showChangePassword, setShowChangePassword] = useState(false)
  const [currentPassword, setCurrentPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [showCurPw, setShowCurPw] = useState(false)
  const [showNewPw, setShowNewPw] = useState(false)
  const [changingPassword, setChangingPassword] = useState(false)
  const [pwMessage, setPwMessage] = useState("")
  const [pwMessageType, setPwMessageType] = useState("")

  useEffect(() => {
    if (!token) {
      navigate("/login")
    }
  }, [token, navigate])

  useEffect(() => {
    if (searchParams.get("edit") === "true" && editRef.current) {
      editRef.current.scrollIntoView({ behavior: "smooth", block: "start" })
    }
  }, [searchParams])

  const handleSave = async (e) => {
    e.preventDefault()
    setSaving(true)
    setMessage("")

    try {
      const res = await fetch(`${API_BASE}/api/auth/profile`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: name.trim(),
          phone: phone.trim(),
          address: address.trim(),
          photo_url: photoUrl.trim(),
        }),
      })

      const data = await res.json()

      if (res.ok) {
        updateUser(data)
        setMessageType("success")
        setMessage("Profile updated successfully")
      } else {
        setMessageType("error")
        setMessage(data.detail || "Failed to update profile")
      }
    } catch {
      setMessageType("error")
      setMessage("Server not reachable")
    } finally {
      setSaving(false)
    }
  }

  const handlePhotoUpload = () => {
    const input = document.createElement("input")
    input.type = "file"
    input.accept = "image/*"
    input.onchange = (e) => {
      const file = e.target.files?.[0]
      if (!file) return
      const reader = new FileReader()
      reader.onload = (ev) => {
        const img = new Image()
        img.onload = () => {
          // Downscale to max 256px so the base64 payload stays small
          const MAX = 256
          let { width, height } = img
          if (width > height && width > MAX) {
            height = Math.round((height * MAX) / width)
            width = MAX
          } else if (height > MAX) {
            width = Math.round((width * MAX) / height)
            height = MAX
          }
          const canvas = document.createElement("canvas")
          canvas.width = width
          canvas.height = height
          canvas.getContext("2d").drawImage(img, 0, 0, width, height)
          setPhotoUrl(canvas.toDataURL("image/jpeg", 0.8))
        }
        img.src = ev.target?.result || ""
      }
      reader.readAsDataURL(file)
    }
    input.click()
  }

  const handleChangePassword = async (e) => {
    e.preventDefault()
    setChangingPassword(true)
    setPwMessage("")

    try {
      const res = await fetch(`${API_BASE}/api/auth/change-password`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      })

      const data = await res.json()

      if (res.ok) {
        setPwMessageType("success")
        setPwMessage("Password changed successfully")
        setCurrentPassword("")
        setNewPassword("")
        setShowChangePassword(false)
      } else {
        setPwMessageType("error")
        setPwMessage(data.detail || "Failed to change password")
      }
    } catch {
      setPwMessageType("error")
      setPwMessage("Server not reachable")
    } finally {
      setChangingPassword(false)
    }
  }

  return (
    <div className="min-h-screen bg-black relative overflow-hidden">
      <BackgroundEffects />
      <ParticleField />

      <div className="relative z-10 max-w-5xl mx-auto px-4 py-20">
        <button
          onClick={() => { if (window.history.length > 1) { navigate(-1) } else { navigate("/home") } }}
          className="flex items-center gap-2 px-5 py-3 mb-6 rounded-full border border-white/10 bg-white/5 hover:border-gold/30 hover:text-gold text-white/60 transition-all cursor-pointer"
        >
          <ArrowLeft size={18} />
          <span className="text-sm font-medium">Back</span>
        </button>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="grid lg:grid-cols-3 gap-8"
        >
          {/* LEFT COLUMN - Avatar & Key Info */}
          <div className="lg:col-span-1">
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-6 text-center">
              <div className="relative mx-auto mb-4 w-fit">
                <div className="w-28 h-28 rounded-full bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center overflow-hidden border-2 border-gold/30 mx-auto">
                  {photoUrl ? (
                    <img src={photoUrl} alt="" className="w-full h-full object-cover" />
                  ) : (
                    <span className="text-black font-bold text-4xl">
                      {(user?.name || "U").charAt(0).toUpperCase()}
                    </span>
                  )}
                </div>
                <button
                  onClick={handlePhotoUpload}
                  className="absolute bottom-1 right-1 w-8 h-8 rounded-full bg-gold flex items-center justify-center hover:bg-gold-dark transition-colors"
                >
                  <Camera size={14} className="text-black" />
                </button>
              </div>

              <h2 className="font-poppins font-bold text-xl text-white mb-1">
                {user?.name || "User"}
              </h2>

              <div className="space-y-3 mt-6 text-left">
                <div className="flex items-center gap-3 text-sm text-white/60">
                  <Mail size={14} className="text-gold/60 shrink-0" />
                  <span className="truncate">{user?.email}</span>
                </div>
                <div className="flex items-center gap-3 text-sm text-white/60">
                  <Phone size={14} className="text-gold/60 shrink-0" />
                  <span>{user?.phone || "No phone added"}</span>
                </div>
                <div className="flex items-start gap-3 text-sm text-white/60">
                  <MapPin size={14} className="text-gold/60 shrink-0 mt-0.5" />
                  <span>{user?.address || "No address added"}</span>
                </div>
              </div>
            </div>
          </div>

          {/* RIGHT COLUMN - Edit Form */}
          <div className="lg:col-span-2">
            <div className="rounded-2xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-6">
              <h3 ref={editRef} className="font-poppins font-semibold text-lg text-white mb-6">
                Edit Profile
              </h3>

              <form onSubmit={handleSave} className="space-y-5">
                <div>
                  <label className="block text-sm text-white/60 mb-2">Full Name</label>
                  <div className="relative">
                    <User size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
                    <input
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      className="w-full pl-9 pr-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-gold/50 transition-colors"
                      required
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm text-white/60 mb-2">Email</label>
                  <div className="relative">
                    <Mail size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
                    <input
                      type="email"
                      value={user?.email || ""}
                      disabled
                      className="w-full pl-9 pr-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white/40 text-sm cursor-not-allowed"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm text-white/60 mb-2">Phone Number</label>
                  <div className="relative">
                    <Phone size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
                    <input
                      type="tel"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      placeholder="+1 (555) 123-4567"
                      className="w-full pl-9 pr-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-gold/50 transition-colors"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm text-white/60 mb-2">Address</label>
                  <div className="relative">
                    <MapPin size={14} className="absolute left-3 top-3 text-white/30" />
                    <textarea
                      value={address}
                      onChange={(e) => setAddress(e.target.value)}
                      placeholder="123 Main St, City, Country"
                      rows={3}
                      className="w-full pl-9 pr-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-gold/50 transition-colors resize-none"
                    />
                  </div>
                </div>

                {message && (
                  <p
                    className={`text-sm text-center ${
                      messageType === "success" ? "text-green-400" : "text-red-400"
                    }`}
                  >
                    {message}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={saving}
                  className="w-full py-3 text-sm font-medium text-black bg-gradient-to-r from-gold-dark to-gold rounded-full hover:shadow-[0_0_30px_rgba(255,179,71,0.15)] transition-shadow disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {saving ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save size={16} />
                      Save Changes
                    </>
                  )}
                </button>
              </form>

              {/* PASSWORD CHANGE */}
              <div className="mt-8 pt-6 border-t border-white/10">
                <button
                  onClick={() => setShowChangePassword(!showChangePassword)}
                  className="flex items-center gap-2 text-sm text-white/60 hover:text-gold transition-colors"
                >
                  <Lock size={14} />
                  {showChangePassword ? "Cancel" : "Change Password"}
                </button>

                {showChangePassword && (
                  <motion.form
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    onSubmit={handleChangePassword}
                    className="mt-4 space-y-4"
                  >
                    <div>
                      <label className="block text-sm text-white/60 mb-2">Current Password</label>
                      <div className="relative">
                        <input
                          type={showCurPw ? "text" : "password"}
                          value={currentPassword}
                          onChange={(e) => setCurrentPassword(e.target.value)}
                          className="w-full pr-10 pl-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-gold/50 transition-colors"
                          required
                        />
                        <button
                          type="button"
                          onClick={() => setShowCurPw(!showCurPw)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60"
                        >
                          {showCurPw ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                    </div>

                    <div>
                      <label className="block text-sm text-white/60 mb-2">New Password</label>
                      <div className="relative">
                        <input
                          type={showNewPw ? "text" : "password"}
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          className="w-full pr-10 pl-4 py-3 bg-white/5 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-gold/50 transition-colors"
                          required
                        />
                        <button
                          type="button"
                          onClick={() => setShowNewPw(!showNewPw)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/60"
                        >
                          {showNewPw ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                      <p className="text-xs text-white/30 mt-1">
                        Min 8 chars, uppercase, lowercase, and a number
                      </p>
                    </div>

                    {pwMessage && (
                      <p
                        className={`text-sm text-center ${
                          pwMessageType === "success" ? "text-green-400" : "text-red-400"
                        }`}
                      >
                        {pwMessage}
                      </p>
                    )}

                    <button
                      type="submit"
                      disabled={changingPassword}
                      className="w-full py-3 text-sm font-medium text-white border border-gold/30 rounded-full hover:bg-gold/10 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                      {changingPassword ? (
                        <>
                          <Loader2 size={16} className="animate-spin" />
                          Updating...
                        </>
                      ) : (
                        <>
                          <Lock size={16} />
                          Update Password
                        </>
                      )}
                    </button>
                  </motion.form>
                )}
              </div>

              {/* SIGN OUT */}
              <div className="mt-6 text-center">
                <button
                  onClick={() => { logout(); navigate("/") }}
                  className="text-sm text-red-400/70 hover:text-red-400 transition-colors"
                >
                  Sign Out
                </button>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
