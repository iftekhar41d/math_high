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

export const listItems = () => request('/items')

export const createItem = (item) =>
  request('/items', { method: 'POST', body: JSON.stringify(item) })

export const deleteItem = (id) => request(`/items/${id}`, { method: 'DELETE' })
