import { useEffect, useState, useCallback } from "react"
import {
  Users,
  Activity,
  AlertTriangle,
  Search,
  Video,
  UserPlus,
  Cpu,
  RefreshCw,
} from "lucide-react"
import { apiFetch } from "../../services/api"
import { Card, SectionHeader, StatCard, ProgressBar, StatusDot } from "../components/ui"

export default function AdminDashboard() {
  const [stats, setStats] = useState(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    setError("")
    try {
      const data = await apiFetch("/api/admin/stats")
      setStats(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(() => load(true), 30000)
    return () => clearInterval(t)
  }, [load])

  const refresh = async () => {
    setRefreshing(true)
    await load(true)
    setRefreshing(false)
  }

  const t = stats?.totals
  const maxDet = stats
    ? Math.max(1, ...stats.detections_7d.map((d) => d.detections))
    : 1

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Platform Overview"
        subtitle="Live metrics from the HaloVision database"
        action={
          <button
            onClick={refresh}
            disabled={refreshing}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm text-white/70 hover:text-gold border border-white/10 hover:border-gold/30 transition-colors"
          >
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        }
      />

      {error && (
        <div className="rounded-xl border border-red-500/25 bg-red-500/5 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        <StatCard label="Total Users" value={t?.users} icon={Users} accent="gold" loading={loading} />
        <StatCard label="Active Users" value={t?.active} icon={Activity} accent="green" loading={loading} />
        <StatCard label="Paid Users" value={t?.paid} icon={UserPlus} accent="blue" loading={loading} />
        <StatCard label="Detections" value={t?.detections} icon={Video} accent="gold" loading={loading} />
        <StatCard label="Alerts" value={t?.alerts} icon={AlertTriangle} accent="red" loading={loading} />
        <StatCard label="Searches" value={t?.searches} icon={Search} accent="blue" loading={loading} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* 7-day detections chart */}
        <Card className="xl:col-span-2">
          <SectionHeader title="Detections — Last 7 Days" subtitle="Real detection volume per day" />
          {loading ? (
            <div className="h-56 rounded-xl bg-white/5 animate-pulse" />
          ) : (
            <div className="h-56 flex items-end gap-3 px-1">
              {stats.detections_7d.map((d) => (
                <div key={d.date} className="flex-1 flex flex-col items-center gap-2 h-full justify-end">
                  <span className="text-xs text-white/50">{d.detections || ""}</span>
                  <div
                    className="w-full max-w-14 rounded-t-lg bg-gradient-to-t from-gold-dark to-gold-light transition-all duration-700"
                    style={{ height: `${Math.max(3, (d.detections / maxDet) * 100)}%` }}
                  />
                  <span className="text-[11px] text-white/40 whitespace-nowrap">{d.date}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Server status */}
        <Card>
          <SectionHeader title="Server Health" subtitle="Local host vitals" />
          <div className="space-y-5">
            {loading ? (
              <div className="space-y-4">
                {[0, 1, 2, 3].map((i) => (
                  <div key={i} className="h-8 rounded-lg bg-white/5 animate-pulse" />
                ))}
              </div>
            ) : (
              <>
                <StatusDot ok={!error} label="API" />
                <StatusDot ok={stats?.server?.gpu !== false} label="Smart Models (GPU / CPU)" />
                <ProgressBar label="CPU" value={stats?.server?.cpu || 0} color="bg-gold" />
                <ProgressBar label="Memory" value={stats?.server?.ram || 0} color="bg-sky-400" />
                {stats?.server?.gpu?.available ? (
                  <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 flex items-center gap-3">
                    <Cpu size={16} className="text-gold shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs text-white/70 truncate">{stats.server.gpu.device}</p>
                      <p className="text-[11px] text-white/40">
                        {stats.server.gpu.memory_used_mb} MB allocated
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 flex items-center gap-3">
                    <Cpu size={16} className="text-white/50 shrink-0" />
                    <p className="text-xs text-white/50">No GPU detected — running on CPU</p>
                  </div>
                )}
              </>
            )}
          </div>
        </Card>
      </div>

      {/* 24h activity strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Detections (24h)", value: t?.detections_24h, icon: Video },
          { label: "Sessions (24h)", value: t?.sessions_24h, icon: Activity },
          { label: "Alerts (24h)", value: t?.alerts_24h, icon: AlertTriangle },
          { label: "New Signups (24h)", value: t?.signups_24h, icon: UserPlus },
        ].map(({ label, value, icon }) => (
          <StatCard key={label} label={label} value={value} icon={icon} accent="gold" loading={loading} />
        ))}
      </div>
    </div>
  )
}