import { useEffect, useState } from "react"
import { Flag, Loader2 } from "lucide-react"
import { apiFetch } from "../../services/api"
import { Card, SectionHeader } from "../components/ui"
import { cn } from "../../lib/utils"

export default function AdminFlags() {
  const [flags, setFlags] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busyKey, setBusyKey] = useState(null)
  const [error, setError] = useState("")

  useEffect(() => {
    apiFetch("/api/admin/feature-flags")
      .then(setFlags)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const toggle = async (key, enabled) => {
    setBusyKey(key)
    try {
      const res = await apiFetch(`/api/admin/feature-flags/${key}`, {
        method: "PATCH",
        body: { key, enabled },
      })
      setFlags((prev) =>
        prev.map((f) => (f.key === key ? { ...f, enabled: res.enabled } : f))
      )
    } catch (e) {
      setError(e.message)
    } finally {
      setBusyKey(null)
    }
  }

  const groups = (flags || []).reduce((acc, f) => {
    ;(acc[f.category] = acc[f.category] || []).push(f)
    return acc
  }, {})

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Feature Flags"
        subtitle="Toggle platform capabilities — changes apply without a restart"
      />

      {error && (
        <div className="rounded-xl border border-red-500/25 bg-red-500/5 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading && (
        <Card>
          <div className="flex justify-center py-12">
            <Loader2 size={22} className="animate-spin text-gold" />
          </div>
        </Card>
      )}

      {!loading &&
        Object.entries(groups).map(([category, items]) => (
          <Card key={category}>
            <h3 className="font-medium text-white capitalize mb-4 flex items-center gap-2">
              <Flag size={15} className="text-gold" />
              {category.replace("_", " ")}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {items.map((f) => (
                <div
                  key={f.key}
                  className={cn(
                    "flex items-center justify-between rounded-xl border px-4 py-3.5 transition-colors",
                    f.enabled
                      ? "border-gold/20 bg-gold/5"
                      : "border-white/10 bg-white/[0.02]"
                  )}
                >
                  <div>
                    <p className="text-sm text-white font-medium">{f.label || f.key}</p>
                    <p className="text-xs text-white/40 font-mono">{f.key}</p>
                  </div>
                  <button
                    onClick={() => toggle(f.key, !f.enabled)}
                    disabled={busyKey === f.key}
                    className={cn(
                      "relative w-12 h-6.5 rounded-full transition-colors disabled:opacity-50",
                      f.enabled ? "bg-gold" : "bg-white/10"
                    )}
                    style={{ height: 26 }}
                    aria-label={`Toggle ${f.key}`}
                  >
                    <span
                      className={cn(
                        "absolute top-0.5 w-5.5 h-5.5 rounded-full bg-white shadow transition-all",
                        f.enabled ? "left-6" : "left-0.5"
                      )}
                      style={{ width: 22, height: 22, top: 2 }}
                    />
                  </button>
                </div>
              ))}
            </div>
          </Card>
        ))}
    </div>
  )
}