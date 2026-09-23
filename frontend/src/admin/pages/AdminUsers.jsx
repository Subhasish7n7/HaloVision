import { useCallback, useEffect, useMemo, useState } from "react"
import {
  Search,
  ChevronLeft,
  ChevronRight,
  Pencil,
  Trash2,
  KeyRound,
  Eye,
  Download,
  Loader2,
  X,
  RefreshCw,
} from "lucide-react"
import { apiFetch } from "../../services/api"
import { Card, SectionHeader, RoleBadge } from "../components/ui"
import { cn } from "../../lib/utils"

const ROLES = ["free", "premium", "support", "moderator", "admin", "super_admin"]

export default function AdminUsers() {
  const [query, setQuery] = useState("")
  const [search, setSearch] = useState("")
  const [role, setRole] = useState("")
  const [status, setStatus] = useState("")
  const [sort, setSort] = useState("-id")
  const [page, setPage] = useState(1)
  const [perPage] = useState(15)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [notify, setNotify] = useState(null)

  // selection ID → prefetched profile detail
  const [detail, setDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [editUser, setEditUser] = useState(null)
  const [confirmDelete, setConfirmDelete] = useState(null)
  const [busyId, setBusyId] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError("")
    try {
      const params = new URLSearchParams()
      if (search) params.set("search", search)
      if (role) params.set("role", role)
      if (status) params.set("status", status)
      params.set("sort", sort)
      params.set("page", page)
      params.set("per_page", perPage)
      const res = await apiFetch(`/api/admin/users?${params.toString()}`)
      setData(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [search, role, status, sort, page, perPage])

  useEffect(() => {
    const t = setTimeout(() => setSearch(query), 400)
    return () => clearTimeout(t)
  }, [query])

  useEffect(() => {
    setPage(1)
  }, [search, role, status])

  useEffect(() => {
    load()
  }, [load])

  const users = useMemo(() => data?.users || [], [data])
  const totalPages = Math.max(1, Math.ceil((data?.total || 0) / perPage))

  const flash = (msg) => {
    setNotify(msg)
    setTimeout(() => setNotify(null), 3500)
  }

  const openDetail = async (u) => {
    setDetailLoading(true)
    setDetail(u)
    try {
      const full = await apiFetch(`/api/admin/users/${u.id}`)
      setDetail(full)
    } catch (err) {
      flash(err.message)
    } finally {
      setDetailLoading(false)
    }
  }

  const patchUser = async (id, body) => {
    setBusyId(id)
    try {
      const updated = await apiFetch(`/api/admin/users/${id}`, {
        method: "PATCH",
        body,
      })
      flash(`Saved changes for ${updated.email}`)
      setData((prev) => ({
        ...prev,
        users: prev.users.map((u) => (u.id === id ? updated : u)),
      }))
      if (detail?.id === id) setDetail((d) => ({ ...d, ...updated }))
      return updated
    } catch (err) {
      flash(err.message)
      return null
    } finally {
      setBusyId(null)
    }
  }

  const resetPassword = async (u) => {
    setBusyId(u.id)
    try {
      const res = await apiFetch(`/api/admin/users/${u.id}/reset-password`, { method: "POST" })
      setNotify(
        `Temporary password for ${u.email}: ${res.temp_password}`
      )
    } catch (err) {
      flash(err.message)
    } finally {
      setBusyId(null)
    }
  }

  const deleteUser = async (u) => {
    setBusyId(u.id)
    try {
      await apiFetch(`/api/admin/users/${u.id}`, { method: "DELETE" })
      setConfirmDelete(null)
      flash(`Deleted ${u.email}`)
      load()
    } catch (err) {
      flash(err.message)
    } finally {
      setBusyId(null)
    }
  }

  const exportCsv = () => {
    const rows = [
      ["id", "name", "email", "role", "active", "banned", "verified", "detections", "sessions", "alerts", "searches", "last_login_at"],
      ...users.map((u) => [
        u.id,
        u.name,
        u.email,
        u.role,
        u.is_active,
        u.is_banned,
        u.is_email_verified,
        u.detections,
        u.sessions,
        u.alerts,
        u.search_queries,
        u.last_login_at,
      ]),
    ]
    const csv = rows.map((r) => r.map(escapeCsv).join(",")).join("\n")
    const blob = new Blob([csv], { type: "text/csv" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `users_page_${page}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const columnHeader = (key, label) => (
    <SortHeader sort={sort} onSort={setSort} dataKey={key} label={label} />
  )

  return (
    <div className="space-y-6">
      <SectionHeader
        title="User Management"
        subtitle={`${data?.total ?? "—"} users total`}
        action={
          <button
            onClick={exportCsv}
            disabled={!users.length}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm text-white/70 hover:text-gold border border-white/10 hover:border-gold/30 transition-colors disabled:opacity-40"
          >
            <Download size={14} />
            Export CSV
          </button>
        }
      />

      {notify && (
        <div className="rounded-xl border border-gold/25 bg-gold/10 px-4 py-3 text-sm text-gold">
          {notify}
        </div>
      )}

      <Card>
        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 mb-5">
          <div className="relative flex-1 min-w-52">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/40" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name or email..."
              className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-white/5 border border-white/10 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-gold/50 transition-colors"
            />
          </div>

          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="px-3 py-2.5 rounded-xl bg-white/5 border border-white/10 text-sm text-white focus:outline-none focus:border-gold/50"
          >
            <option value="">All roles</option>
            {ROLES.map((r) => (
              <option key={r} value={r} className="bg-black">
                {r.replace("_", " ")}
              </option>
            ))}
          </select>

          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="px-3 py-2.5 rounded-xl bg-white/5 border border-white/10 text-sm text-white focus:outline-none focus:border-gold/50"
          >
            <option value="">All statuses</option>
            <option value="active" className="bg-black">Active</option>
            <option value="banned" className="bg-black">Banned</option>
          </select>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-white/40 text-xs border-b border-white/10">
                <th className="py-3 pr-4">{columnHeader("name", "User")}</th>
                <th className="py-3 pr-4">Role</th>
                <th className="py-3 pr-4">Status</th>
                <th className="py-3 pr-4">{columnHeader("last_login_at", "Last Login")}</th>
                <th className="py-3 pr-4">Usage</th>
                <th className="py-3 pr-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={6}>
                    <div className="py-8 flex justify-center">
                      <Loader2 size={22} className="animate-spin text-gold" />
                    </div>
                  </td>
                </tr>
              )}

              {!loading && users.length === 0 && (
                <tr>
                  <td colSpan={6}>
                    <div className="py-10 text-center text-white/40">
                      No users match your filters.
                    </div>
                  </td>
                </tr>
              )}

              {!loading &&
                users.map((u) => (
                  <tr key={u.id} className="border-b border-white/5 hover:bg-white/[0.03] transition-colors">
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-gradient-to-br from-gold to-gold-dark flex items-center justify-center shrink-0">
                          <span className="text-black font-bold text-xs">
                            {(u.name || "?").charAt(0).toUpperCase()}
                          </span>
                        </div>
                        <div className="min-w-0">
                          <p className="text-white font-medium truncate">{u.name}</p>
                          <p className="text-white/40 text-xs truncate">{u.email}</p>
                        </div>
                      </div>
                    </td>
                    <td className="py-3 pr-4"><RoleBadge role={u.role} /></td>
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            "w-2 h-2 rounded-full",
                            u.is_banned
                              ? "bg-red-400"
                              : u.is_active
                              ? "bg-emerald-400"
                              : "bg-white/30"
                          )}
                        />
                        <span className="text-xs text-white/50">
                          {u.is_banned ? "Banned" : u.is_active ? "Active" : "Disabled"}
                        </span>
                      </div>
                    </td>
                    <td className="py-3 pr-4 text-white/50 text-xs">
                      {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "never"}
                    </td>
                    <td className="py-3 pr-4 text-white/50 text-xs">
                      {u.detections} det · {u.sessions} sess
                    </td>
                    <td className="py-3 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-1">
                        <ActionBtn title="View" onClick={() => openDetail(u)} icon={<Eye size={14} />} />
                        <ActionBtn title="Edit" onClick={() => setEditUser(u)} icon={<Pencil size={14} />} disabled={busyId === u.id} />
                        <ActionBtn title="Reset password" onClick={() => resetPassword(u)} icon={busyId === u.id ? <Loader2 size={14} className="animate-spin" /> : <KeyRound size={14} />} />
                        <ActionBtn title="Delete" danger onClick={() => setConfirmDelete(u)} icon={<Trash2 size={14} />} />
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {!loading && users.length > 0 && (
          <div className="flex items-center justify-between mt-4">
            <p className="text-white/40 text-xs">
              Showing {(page - 1) * perPage + 1}–{Math.min(page * perPage, data.total)} of {data.total}
            </p>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="p-2 rounded-lg text-white/60 hover:text-gold disabled:opacity-30"
              >
                <ChevronLeft size={16} />
              </button>
              <span className="text-sm text-white/60 px-2">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="p-2 rounded-lg text-white/60 hover:text-gold disabled:opacity-30"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </Card>

      {/* --- User detail modal --- */}
      {detail && (
        <Modal onClose={() => setDetail(null)}>
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="font-poppins text-lg font-semibold text-white">{detail.name}</h3>
              <p className="text-white/40 text-sm">{detail.email}</p>
            </div>
            <RoleBadge role={detail.role} />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <KV label="Role" value={detail.role} />
            <KV label="Active" value={detail.is_active ? "Yes" : "No"} />
            <KV label="Verified" value={detail.is_email_verified ? "Yes" : "No"} />
            <KV label="Detections" value={detail.detections} />
            <KV label="Sessions" value={detail.sessions} />
            <KV label="Alerts" value={detail.alerts} />
            <KV label="Searches" value={detail.search_queries} />
            <KV label="Last login" value={detail.last_login_at ? new Date(detail.last_login_at).toLocaleString() : "never"} />
            <KV label="Joined" value={detail.created_at ? new Date(detail.created_at).toLocaleDateString() : "—"} />
            <KV label="Suspend" value={detail.is_banned ? "Banned" : "—"} />
          </div>

          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-medium text-white">Login History</h4>
            <button
              onClick={() => openDetail(detail)}
              className="flex items-center gap-2 text-xs text-gold hover:text-gold-light"
            >
              <RefreshCw size={12} /> Reload
            </button>
          </div>

          {detailLoading ? (
            <div className="space-y-2">
              {[0, 1, 2].map((i) => (
                <div key={i} className="h-12 rounded-lg bg-white/5 animate-pulse" />
              ))}
            </div>
          ) : detail.logins?.length ? (
            <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
              {detail.logins.map((l, i) => (
                <div key={i} className="flex items-center justify-between gap-3 rounded-xl bg-white/[0.03] border border-white/5 px-4 py-2.5 text-sm">
                  <span className={cn("text-xs font-medium", l.success ? "text-emerald-400" : "text-red-400")}>
                    {l.success ? "Success" : "Failed"}
                  </span>
                  <span className="text-white/50 text-xs truncate">{l.ip || "unknown ip"}</span>
                  <span className="text-white/40 text-xs truncate">{l.user_agent || "—"}</span>
                  <span className="text-white/40 text-xs whitespace-nowrap">
                    {l.timestamp ? new Date(l.timestamp).toLocaleString() : "—"}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-white/40 text-sm py-4 text-center">
              No login history recorded yet.
            </p>
          )}
        </Modal>
      )}

      {/* Edit user modal */}
      {editUser && (
        <EditModal
          user={editUser}
          onClose={() => setEditUser(null)}
          onSave={async (body) => {
            const updated = await patchUser(editUser.id, body)
            if (updated) setEditUser(null)
          }}
          busy={busyId === editUser.id}
        />
      )}

      {/* Delete confirm */}
      {confirmDelete && (
        <Modal onClose={() => setConfirmDelete(null)}>
          <h3 className="text-lg font-semibold text-white mb-2">Delete user</h3>
          <p className="text-white/50 text-sm mb-6">
            This permanently removes <span className="text-white">{confirmDelete.email}</span> and all of their
            detections, sessions, alerts, search history and preference data. This cannot be undone.
          </p>
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setConfirmDelete(null)}
              className="px-4 py-2 rounded-xl text-sm text-white/60 hover:text-white border border-white/10"
            >
              Cancel
            </button>
            <button
              onClick={() => deleteUser(confirmDelete)}
              disabled={busyId === confirmDelete.id}
              className="px-4 py-2 rounded-xl text-sm font-medium text-white bg-red-500/80 hover:bg-red-500 disabled:opacity-50"
            >
              {busyId === confirmDelete.id ? "Deleting..." : "Delete permanently"}
            </button>
          </div>
        </Modal>
      )}

      <span className="sr-only" />
    </div>
  )
}

// ---------- small pieces ----------

function SortHeader({ sort, onSort, dataKey, label }) {
  return (
    <button
      onClick={() => onSort(sort === dataKey ? `-${dataKey}` : dataKey)}
      className="flex items-center gap-1 hover:text-gold transition-colors"
    >
      {label}
      <span className="text-white/40">
        {sort === dataKey ? "▲" : sort === `-${dataKey}` ? "▼" : "⇅"}
      </span>
    </button>
  )
}

function escapeCsv(v) {
  const s = String(v ?? "")
  return /\s|,|"/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function ActionBtn({ onClick, icon, title, disabled }) {
  return (
    <button
      title={title}
      onClick={onClick}
      disabled={disabled}
      className="p-2 rounded-lg text-white/40 hover:text-gold hover:bg-gold/10 transition-colors disabled:opacity-30"
    >
      {icon}
    </button>
  )
}

function KV({ label, value }) {
  return (
    <div className="rounded-xl bg-white/[0.03] border border-white/5 px-3 py-2.5">
      <p className="text-[11px] text-white/40 uppercase tracking-wide">{label}</p>
      <p className="text-white/80 text-sm mt-0.5">{value ?? "—"}</p>
    </div>
  )
}

function Modal({ onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/70" onClick={onClose} />
      <div className="relative w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-2xl border border-white/10 bg-black/95 backdrop-blur-2xl p-6 shadow-2xl">
        <button onClick={onClose} className="absolute top-4 right-4 text-white/40 hover:text-white">
          <X size={18} />
        </button>
        {children}
      </div>
    </div>
  )
}

function EditModal({ user, onClose, onSave, busy }) {
  const [role, setRole] = useState(user.role)
  const [active, setActive] = useState(user.is_active)
  const [banned, setBanned] = useState(user.is_banned)
  const [verified, setVerified] = useState(user.is_email_verified)

  return (
    <Modal onClose={onClose}>
      <h3 className="text-lg font-semibold text-white mb-1">Edit user</h3>
      <p className="text-white/40 text-sm mb-6">{user.email}</p>

      <div className="grid grid-cols-2 gap-4 mb-6">
        <div>
          <label className="block text-xs text-white/60 mb-1.5">Role</label>
          <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full px-3 py-2.5 rounded-xl bg-white/5 border border-white/10 text-sm text-white focus:outline-none focus:border-gold/50">
            {ROLES.map((r) => (
              <option key={r} value={r} className="bg-black">{r.replace("_", " ")}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="space-y-3 mb-6">
        {[
          { label: "Active account", checked: active, set: setActive, name: "active" },
          { label: "Banned", checked: banned, set: setBanned, name: "banned" },
          { label: "Email verified", checked: verified, set: setVerified, name: "verified" },
        ].map(({ label, checked, set, name }) => (
          <label key={name} className="flex items-center justify-between cursor-pointer rounded-xl bg-white/[0.03] border border-white/5 px-4 py-3">
            <span className="text-sm text-white/70">{label}</span>
            <input type="checkbox" checked={checked} onChange={(e) => set(e.target.checked)} className="accent-gold" />
          </label>
        ))}
      </div>

      <div className="flex justify-end gap-3">
        <button onClick={onClose} className="px-4 py-2 rounded-xl text-sm text-white/60 hover:text-white border border-white/10">
          Cancel
        </button>
        <button
          disabled={busy}
          onClick={() => onSave({ role, is_active: active, is_banned: banned, is_email_verified: verified })}
          className="px-5 py-2 rounded-xl text-sm font-medium text-black bg-gradient-to-r from-gold-dark to-gold disabled:opacity-50"
        >
          {busy ? "Saving..." : "Save changes"}
        </button>
      </div>
    </Modal>
  )
}