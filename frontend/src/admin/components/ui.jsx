import { cn } from "../../lib/utils"

export function Card({ className, children }) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-white/10 bg-white/[0.02] backdrop-blur-xl p-5",
        className
      )}
    >
      {children}
    </div>
  )
}

export function SectionHeader({ title, subtitle, action }) {
  return (
    <div className="flex items-center justify-between gap-4 mb-5">
      <div>
        <h2 className="font-poppins text-lg font-semibold text-white">{title}</h2>
        {subtitle && <p className="text-white/40 text-sm mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

export function StatCard({ label, value, sub, icon: Icon, accent = "gold", loading }) {
  return (
    <Card className="hover:shadow-[0_0_30px_rgba(255,179,71,0.12)] transition-shadow duration-500">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-white/50 text-xs uppercase tracking-wider truncate">
            {label}
          </p>
          {loading ? (
            <div className="mt-2 h-8 w-16 rounded-lg bg-white/5 animate-pulse" />
          ) : (
            <p className="mt-1 text-3xl font-poppins font-bold text-white">
              {value ?? "—"}
            </p>
          )}
          {sub && <p className="text-white/40 text-xs mt-1">{sub}</p>}
        </div>
        <div
          className={cn(
            "w-10 h-10 rounded-xl flex items-center justify-center shrink-0 border",
            accent === "red"
              ? "bg-red-500/10 border-red-500/20 text-red-400"
              : accent === "green"
              ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
              : accent === "blue"
              ? "bg-sky-500/10 border-sky-500/20 text-sky-400"
              : "bg-gold/10 border-gold/20 text-gold"
          )}
        >
          {Icon && <Icon size={18} />}
        </div>
      </div>
    </Card>
  )
}

export function SkeletonRows({ rows = 4, cols = 4 }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-3">
          {Array.from({ length: cols }).map((_, c) => (
            <div
              key={c}
              className="flex-1 h-10 rounded-lg bg-white/5 animate-pulse"
            />
          ))}
        </div>
      ))}
    </div>
  )
}

export function ProgressBar({ value = 0, max = 100, color = "bg-gold", label }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <div>
      {label && (
        <div className="flex justify-between text-xs mb-1.5">
          <span className="text-white/60">{label}</span>
          <span className="text-white/80 font-medium">{pct}%</span>
        </div>
      )}
      <div className="h-2 rounded-full bg-white/5 overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-700", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export function RoleBadge({ role }) {
  const styles = {
    super_admin: "bg-red-500/10 text-red-300 border-red-500/25",
    admin: "bg-gold/10 text-gold border-gold/25",
    moderator: "bg-sky-500/10 text-sky-300 border-sky-500/25",
    support: "bg-violet-500/10 text-violet-300 border-violet-500/25",
    premium: "bg-emerald-500/10 text-emerald-300 border-emerald-500/25",
    free: "bg-white/5 text-white/50 border-white/10",
  }
  const key = role || "free"
  return (
    <span
      className={cn(
        "text-[11px] uppercase tracking-wide px-2.5 py-1 rounded-full border inline-flex items-center",
        styles[key] || styles.free
      )}
    >
      {key.replace("_", " ")}
    </span>
  )
}

export function StatusDot({ ok, label }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={cn(
          "w-2.5 h-2.5 rounded-full relative",
          ok ? "bg-emerald-400" : "bg-red-400"
        )}
      >
        {ok && (
          <span className="absolute inset-0 rounded-full bg-emerald-400 animate-ping" />
        )}
      </span>
      <span className="text-sm text-white/60">{label}</span>
    </div>
  )
}