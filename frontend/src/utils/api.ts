const rawBaseUrl = (import.meta.env?.VITE_API_URL ?? '').trim()

const normalizedBaseUrl = rawBaseUrl.endsWith('/') ? rawBaseUrl.slice(0, -1) : rawBaseUrl

export function apiUrl(path: string): string {
  if (!path.startsWith('/')) {
    throw new Error(`API path must start with '/': ${path}`)
  }
  return `${normalizedBaseUrl}${path}`
}
