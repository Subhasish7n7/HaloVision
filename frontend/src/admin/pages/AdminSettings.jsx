import { useEffect, useState } from "react"
import { Loader2, Save, KeyRound } from "lucide-react"
import { apiFetch } from "../../services/api"
import { Card, SectionHeader } from "../components/ui"

export default function AdminSettings() {
  const [settings, setSettings] = useState(null)
  const [draft, setDraft] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    apiFetch("/api/admin/settings")
      .then((res) => {
        setSettings(res.settings)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const setValue = (key, value) =>
    setDraft((prev) => ({ ...prev, [key]: value }))

  const save = async () => {
    setSaving(true)
    setError("")
    try {
      await apiFetch("/api/admin/settings", {
        method: "PUT",
        body: { values: draft },
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <SectionHeader title="System Settings" subtitle="Runtime configuration" />
        <Card>
          <div className="flex justify-center py-12">
            <Loader2 size={22} className="animate-spin text-gold" />
          </div>
        </Card>
      </div>
    )
  }

  const groups = (settings || []).reduce((acc, s) => {
    const g = s.key.includes("_") ? s.key.split("_")[0] : s.key
    ;(acc[g] = acc[g] || []).push(s)
    return acc
  }, {})

  return (
    <div className="space-y-6">
      <SectionHeader
        title="System Settings"
        subtitle="Confidence thresholds, limits, and provider keys"
        action={
          <button
            onClick={save}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-black bg-gradient-to-r from-gold-dark to-gold transition-shadow disabled:opacity-50"
          >
            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            {saved ? "Saved" : "Save changes"}
          </button>
        }
      />

      {error && (
        <div className="rounded-xl border border-red-500/25 bg-red-500/5 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {Object.entries(groups).map(([group, items]) => (
        <Card key={group}>
          <h3 className="font-medium text-white capitalize mb-4">{group}</h3>
          <div className="space-y-4">
            {items.map((s) => (
              <div key={s.key}>
                <label className="flex items-center gap-2 text-sm text-white/70 mb-1.5">
                  {s.is_secret && <KeyRound size={13} className="text-gold" />}
                  {s.key.replace(/_/g, " ")}
                </label>
                <input
                  type={s.is_secret ? "password" : "text"}
                  value={draft[s.key] !== undefined ? draft[s.key] : s.value}
                  onChange={(e) => setValue(s.key, e.target.value)}
                  className="w-full px-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-gold/50 transition-colors"
                />
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  )
}