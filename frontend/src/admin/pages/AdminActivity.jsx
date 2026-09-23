import { useEffect, useState } from "react"
import { Loader2, ShieldCheck } from "lucide-react"
import { apiFetch } from "../../services/api"
import { Card, SectionHeader } from "../components/ui"

const ACTION_STYLES = {
  "user.update": "text-sky-300",
  "user.delete": "text-red-400",
  "user.reset_password": "text-violet-300",
  "flag.update": "text-gold",
  "settings.update": "text-emerald-300",
}

function actionLabel(action) {
  return (action || "unknown").replace(/_/g, " ")
}

export default function AdminActivity() {
  const [activities, setActivities] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    apiFetch("/api/admin/activity")
      .then((res) => setActivities(res.activities))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Audit Log"
        subtitle="Every admin action is recorded with before/after context"
      />

      {error && (
        <div className="rounded-xl border border-red-500/25 bg-red-500/5 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <Card>
        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 size={22} className="animate-spin text-gold" />
          </div>
        ) : !activities?.length ? (
          <div className="py-12 text-center">
            <ShieldCheck size={28} className="mx-auto text-white/30 mb-3" />
            <p className="text-white/40 text-sm">
              No admin activity recorded yet.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {activities.map((a) => (
              <div
                key={a.id}
                className="flex items-start gap-4 rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3.5"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm text-white font-medium">
                      {a.admin_email || "system"}
                    </span>
                    <span
                      className={`text-xs font-medium px-2 py-0.5 rounded-full border border-current/20 bg-white/5 ${ACTION_STYLES[a.action] || "text-white/60"}`}
                    >
                      {actionLabel(a.action)}
                    </span>
                    {a.target && (
                      <span className="text-xs text-white/50 truncate">
                        {a.target}
                      </span>
                    )}
                  </div>
                  {a.detail && (
                    <p className="text-xs text-white/40 mt-1 font-mono truncate">
                      {a.detail}
                    </p>
                  )}
                </div>
                <span className="text-xs text-white/40 whitespace-nowrap">
                  {a.timestamp ? new Date(a.timestamp).toLocaleString() : "—"}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}