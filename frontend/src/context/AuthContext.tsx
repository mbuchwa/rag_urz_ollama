import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'

import { apiUrl } from '../utils/api'

type Namespace = {
  id: string
  slug: string
  name: string
  role: string
}

type User = {
  id: string
  email: string
  displayName: string | null
}

type AuthContextValue = {
  user: User | null
  namespaces: Namespace[]
  csrfToken: string | null
  loading: boolean
  refresh: () => Promise<boolean>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [namespaces, setNamespaces] = useState<Namespace[]>([])
  const [csrfToken, setCsrfToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchMe = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(apiUrl('/auth/me'), { credentials: 'include' })
      if (!res.ok) {
        setUser(null)
        setNamespaces([])
        setCsrfToken(null)
        return false
      }

      const data = await res.json()
      const fetchedUser: User = {
        id: data.user.id,
        email: data.user.email,
        displayName: data.user.display_name ?? null,
      }
      setUser(fetchedUser)
      const rawNamespaces = Array.isArray(data.namespaces) ? data.namespaces : []
      const normalizedNamespaces: Namespace[] = rawNamespaces
        .map((ns: any) => ({
          id: typeof ns?.id === 'string' ? ns.id : '',
          slug: typeof ns?.slug === 'string' ? ns.slug : '',
          name: typeof ns?.name === 'string' ? ns.name : '',
          role: typeof ns?.role === 'string' ? ns.role : '',
        }))
        .filter((ns) => ns.id)
      setNamespaces(normalizedNamespaces)
      setCsrfToken(typeof data.csrf_token === 'string' ? data.csrf_token : null)
      return true
    } catch (error) {
      console.error('Failed to fetch /auth/me', error)
      setUser(null)
      setNamespaces([])
      setCsrfToken(null)
      return false
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchMe()
  }, [fetchMe])

  const logout = useCallback(async () => {
    try {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
      }
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken
      }
      await fetch(apiUrl('/auth/logout'), {
        method: 'POST',
        headers,
        credentials: 'include',
      })
    } catch (error) {
      console.error('Failed to logout', error)
    } finally {
      setUser(null)
      setNamespaces([])
      setCsrfToken(null)
      setLoading(false)
    }
  }, [csrfToken])

  const value = useMemo<AuthContextValue>(
    () => ({ user, namespaces, csrfToken, loading, refresh: fetchMe, logout }),
    [user, namespaces, csrfToken, loading, fetchMe, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
