// Same-origin relative path. Vite's dev proxy and nginx's prod proxy both
// forward /api/* to the FastAPI service, so no base URL config is needed.
const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`)
  }
  if (res.status === 204) return null
  return res.json()
}

// The walking-skeleton round trip: proves web -> nginx -> API -> DB.
export const getMeta = () => request('/meta')
