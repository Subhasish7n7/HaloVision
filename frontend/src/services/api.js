const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"

function getToken() {
  return localStorage.getItem("halo_token") || sessionStorage.getItem("halo_token")
}

export async function apiFetch(path, options = {}) {
  const token = getToken()
  const headers = {
    Authorization: `Bearer ${token}`,
    ...(options.headers || {}),
  }

  let body = options.body
  if (body && typeof body === "object" && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json"
    body = JSON.stringify(body)
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers, body })

  let data = null
  try {
    data = await res.json()
  } catch {
    /* non-JSON response */
  }

  if (!res.ok) {
    const err = new Error(
      data?.detail
        ? typeof data.detail === "string"
          ? data.detail
          : "Request failed"
        : `Request failed (${res.status})`
    )
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

export default { apiFetch, API_BASE }