import { Navigate, useLocation } from "react-router-dom"
import { useAuth } from "../context/AuthContext"
import { ShieldAlert } from "lucide-react"

const ADMIN_ROLES = ["super_admin", "admin", "moderator", "support"]

function AdminDenied() {
  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-6">
      <div className="text-center max-w-md">
        <div className="mx-auto w-20 h-20 rounded-2xl border border-red-500/30 bg-red-500/5 flex items-center justify-center mb-6">
          <ShieldAlert size={36} className="text-red-400" />
        </div>
        <h1 className="font-poppins text-2xl font-bold text-white mb-2">
          403 — Access Denied
        </h1>
        <p className="text-white/50 text-sm leading-relaxed mb-6">
          This area requires an administrator account. Your current role does
          not have permission to access the management console.
        </p>
        <button
          onClick={() => (window.location.href = "/home")}
          className="px-6 py-2.5 text-sm font-medium text-black bg-gradient-to-r from-gold-dark to-gold rounded-full"
        >
          Return to App
        </button>
      </div>
    </div>
  )
}

export default function AdminRoute({ children }) {
  const { token, user, checking } = useAuth()
  const location = useLocation()

  if (checking) return null

  if (!token) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  if (!user || !ADMIN_ROLES.includes(user.role)) {
    return <AdminDenied />
  }

  return children
}