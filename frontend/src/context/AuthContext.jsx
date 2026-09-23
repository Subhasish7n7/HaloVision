import { createContext, useContext, useState, useEffect, useCallback } from "react"

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000"

const AuthContext = createContext(null)

const TOKEN_KEY = "halo_token"
const USER_KEY = "halo_user"
const EMAIL_KEY = "halo_email"

function readSession() {
  const tokenLS = localStorage.getItem(TOKEN_KEY)
  const tokenSS = sessionStorage.getItem(TOKEN_KEY)

  if (tokenLS) {
    try {
      const user = JSON.parse(localStorage.getItem(USER_KEY))
      return { token: tokenLS, user }
    } catch {
      return { token: tokenLS, user: null }
    }
  }

  if (tokenSS) {
    try {
      const user = JSON.parse(sessionStorage.getItem(USER_KEY))
      return { token: tokenSS, user }
    } catch {
      return { token: tokenSS, user: null }
    }
  }

  return { token: null, user: null }
}

export function AuthProvider({ children }) {
  const [{ token, user }, setAuth] = useState(readSession)
  const [checking, setChecking] = useState(!!readSession().token)
  const [savedEmail, setSavedEmail] = useState(() => localStorage.getItem(EMAIL_KEY) || "")

  const persist = useCallback((newToken, userData, remember) => {
    if (remember) {
      sessionStorage.removeItem(TOKEN_KEY)
      sessionStorage.removeItem(USER_KEY)
      localStorage.setItem(TOKEN_KEY, newToken)
      localStorage.setItem(USER_KEY, JSON.stringify(userData))
    } else {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
      sessionStorage.setItem(TOKEN_KEY, newToken)
      sessionStorage.setItem(USER_KEY, JSON.stringify(userData))
    }
    if (userData?.email) {
      localStorage.setItem(EMAIL_KEY, userData.email)
      setSavedEmail(userData.email)
    }
    setAuth({ token: newToken, user: userData })
  }, [])

  const login = useCallback((newToken, userData, remember = false) => {
    persist(newToken, userData, remember)
  }, [persist])

  const updateUser = useCallback((userData) => {
    const storage = localStorage.getItem(TOKEN_KEY) ? localStorage : sessionStorage
    storage.setItem(USER_KEY, JSON.stringify(userData))
    setAuth((prev) => ({ ...prev, user: userData }))
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    sessionStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(USER_KEY)
    localStorage.removeItem(EMAIL_KEY)
    setSavedEmail("")
    setAuth({ token: null, user: null })
  }, [])

  // Validate the stored token on app load
  useEffect(() => {
    let mounted = true

    const validate = async () => {
      const { token: storedToken } = readSession()
      if (!storedToken) {
        setChecking(false)
        return
      }

      try {
        const res = await fetch(`${API_BASE}/api/auth/me`, {
          headers: { Authorization: `Bearer ${storedToken}` },
        })

        if (!mounted) return

        if (res.ok) {
          const freshUser = await res.json()
          const storage = localStorage.getItem(TOKEN_KEY) ? localStorage : sessionStorage
          storage.setItem(USER_KEY, JSON.stringify(freshUser))
          setAuth({ token: storedToken, user: freshUser })
        } else {
          logout()
        }
      } catch {
        // Server unreachable - keep the session but stay logged in
      } finally {
        if (mounted) setChecking(false)
      }
    }

    validate()

    return () => {
      mounted = false
    }
  }, [logout])

  return (
    <AuthContext.Provider value={{ token, user, checking, login, logout, updateUser, savedEmail }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
