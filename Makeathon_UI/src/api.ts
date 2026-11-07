/** Use the hosted API when configured, or the local Vite proxy otherwise. */
const apiOrigin = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')

export function apiUrl(path: string): string {
  return path === '/api' || path.startsWith('/api/') || path.startsWith('/api?')
    ? `${apiOrigin}${path}`
    : path
}
