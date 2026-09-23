import { useState } from "react"
import { NavLink, Outlet, useNavigate } from "react-router-dom"
import { useAuth } from "../../context/AuthContext"
import { cn } from "../../lib/utils"
import {
  LayoutDashboard,
  Users,
  Flag,
  Settings,
  ScrollText,
  LogOut,
  ExternalLink,
  Menu,
  X,
} from "lucide-react"

const NAV_ITEMS = [
  { to: "/admin", end: true, label: "Dashboard", icon: LayoutDashboard },
  { to: "/admin/users", label: "Users", icon: Users },
  { to: "/admin/flags", label: "Feature Flags", icon: Flag },
  { to: "/admin/settings", label: "Settings", icon: Settings },
  { to: "/admin/activity", label: "Activity Log", icon: ScrollText },
]

export default function AdminLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const handleLogout = () => {
    logout()
    navigate("/")
  }

  const sidebar = (
    <div className="flex flex-col h-full">
      <div className="px-5 py-5 flex items-center gap-3 border-b border-white/5">
        <div className="w-9 h-9 rounded-full bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center">
          <span className="text-black font-bold text-sm">H</span>
        </div>
        <div>
          <p className="text-white font-poppins font-semibold text-sm leading-none">
            HaloVision
          </p>
          <p className="text-white/40 text-[11px] mt-1">Admin Console</p>
        </div>
        <button
          onClick={() => setSidebarOpen(false)}
          className="lg:hidden ml-auto text-white/50"
        >
          <X size={18} />
        </button>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map(({ to, end, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors",
                isActive
                  ? "bg-gold/10 text-gold border border-gold/20"
                  : "text-white/60 hover:text-white hover:bg-white/5 border border-transparent"
              )
            }
          >
            <Icon size={17} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-3 py-4 border-t border-white/5 space-y-1">
        <button
          onClick={() => navigate("/")}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-white/60 hover:text-white hover:bg-white/5 transition-colors"
        >
          <ExternalLink size={17} />
          View Site
        </button>
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-red-400/80 hover:text-red-400 hover:bg-red-400/5 transition-colors"
        >
          <LogOut size={17} />
          Sign Out
        </button>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-black text-white flex">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-64 shrink-0 border-r border-white/5 bg-white/[0.02]">
        {sidebar}
      </aside>

      {/* Mobile sidebar */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-black/70"
            onClick={() => setSidebarOpen(false)}
          />
          <aside className="absolute left-0 top-0 h-full w-64 bg-black border-r border-white/10">
            {sidebar}
          </aside>
        </div>
      )}

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-16 shrink-0 border-b border-white/5 bg-white/[0.02] backdrop-blur-xl flex items-center gap-4 px-5">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden text-white/70"
          >
            <Menu size={20} />
          </button>
          <div className="flex-1">
            <p className="text-white font-medium text-sm">Admin Console</p>
            <p className="text-white/40 text-xs">
              Signed in as {user?.email}
            </p>
          </div>
          <span className="text-[11px] uppercase tracking-wider px-3 py-1 rounded-full bg-gold/10 text-gold border border-gold/20">
            {user?.role?.replace("_", " ") || "admin"}
          </span>
        </header>

        <main className="flex-1 overflow-y-auto p-5 lg:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}