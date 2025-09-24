const rawBaseUrl = (import.meta.env?.VITE_API_URL ?? '').trim()

const LOCAL_HOSTNAMES = new Set(['localhost', '127.0.0.1', '[::1]'])

function normalizePath(pathname: string): string {
  if (!pathname || pathname === '/') {
    return ''
  }
  return pathname.endsWith('/') ? pathname.slice(0, -1) : pathname
}

function resolveBaseUrl(): string {
  if (typeof window === 'undefined') {
    return rawBaseUrl.endsWith('/') ? rawBaseUrl.slice(0, -1) : rawBaseUrl
  }

  const windowOrigin = window.location.origin
  const windowHost = window.location.hostname
  const windowHostIsLocal = LOCAL_HOSTNAMES.has(windowHost)

  if (!rawBaseUrl) {
    return windowOrigin
  }

  try {
    const resolved = new URL(rawBaseUrl, windowOrigin)
    const normalizedPath = normalizePath(resolved.pathname)
    const hostIsLocal = LOCAL_HOSTNAMES.has(resolved.hostname)

    if (hostIsLocal && !windowHostIsLocal) {
      return `${windowOrigin}${normalizedPath}`
    }

    return `${resolved.origin}${normalizedPath}`
  } catch (error) {
    console.warn('Failed to parse VITE_API_URL, falling back to raw value', error)
    return rawBaseUrl.endsWith('/') ? rawBaseUrl.slice(0, -1) : rawBaseUrl
  }
}

const baseUrl = resolveBaseUrl()

export function apiUrl(path: string): string {
  if (!path.startsWith('/')) {
    throw new Error(`API path must start with '/': ${path}`)
  }
  return `${baseUrl}${path}`
}
