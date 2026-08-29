// Same-origin relative path. Vite's dev proxy and nginx's prod proxy both
// forward /api/* to the FastAPI service, so no base URL config is needed.
const BASE = '/api'

// The access token lives in memory only (the auth store owns it); the refresh
// token is an httpOnly cookie the browser attaches automatically. A 401 on an
// authenticated call triggers one transparent refresh-and-retry.
let accessToken = null
let refreshHandler = null

export function setAccessToken(token) {
  accessToken = token
}

export function setRefreshHandler(fn) {
  refreshHandler = fn
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : detail?.message || `Request failed: ${status}`)
    this.status = status
    this.detail = detail
  }
}

async function parseError(res) {
  try {
    const body = await res.json()
    return body?.detail ?? body
  } catch {
    return res.statusText
  }
}

async function raw(path, { auth = false, headers = {}, ...options } = {}) {
  const finalHeaders = { 'Content-Type': 'application/json', ...headers }
  if (auth && accessToken) {
    finalHeaders.Authorization = `Bearer ${accessToken}`
  }
  return fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: finalHeaders,
    ...options,
  })
}

async function request(path, options = {}) {
  let res = await raw(path, options)

  if (res.status === 401 && options.auth && !options._retried && refreshHandler) {
    const refreshed = await refreshHandler()
    if (refreshed) {
      res = await raw(path, { ...options, _retried: true })
    }
  }

  if (!res.ok) {
    throw new ApiError(res.status, await parseError(res))
  }
  if (res.status === 204) return null
  return res.json()
}

// -- meta ---------------------------------------------------------------
export const getMeta = () => request('/meta')

// -- auth -------------------------------------------------------------------
export const register = (payload) =>
  request('/auth/register', { method: 'POST', body: JSON.stringify(payload) })

export const verifyEmail = (token) =>
  request('/auth/verify-email', { method: 'POST', body: JSON.stringify({ token }) })

export const resendVerification = (email) =>
  request('/auth/resend-verification', { method: 'POST', body: JSON.stringify({ email }) })

export const login = (email, password) =>
  request('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })

export const refreshSession = () => request('/auth/refresh', { method: 'POST' })

export const logout = () => request('/auth/logout', { method: 'POST' })

export const logoutAll = () => request('/auth/logout-all', { method: 'POST', auth: true })

export const forgotPassword = (email) =>
  request('/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email }) })

export const resetPassword = (token, newPassword) =>
  request('/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ token, new_password: newPassword }),
  })

// -- profile ----------------------------------------------------------------
export const getProfile = () => request('/profile', { auth: true })

export const updateProfile = (payload) =>
  request('/profile', { method: 'PATCH', auth: true, body: JSON.stringify(payload) })

// -- content --------------------------------------------------------------
export const getYearLevels = () => request('/content/year-levels', { auth: true })

export const getSubjects = (yearLevelId) =>
  request(`/content/year-levels/${yearLevelId}/subjects`, { auth: true })

export const getUnits = (subjectId) =>
  request(`/content/subjects/${subjectId}/units`, { auth: true })

export const getTopics = (unitId) =>
  request(`/content/units/${unitId}/topics`, { auth: true })

export const getTopic = (slug) =>
  request(`/content/topics/${encodeURIComponent(slug)}`, { auth: true })

// -- practice -----------------------------------------------------------
export const startPractice = (topicSlug) =>
  request('/practice/sessions', {
    method: 'POST',
    auth: true,
    body: JSON.stringify({ topic_slug: topicSlug }),
  })

export const submitAnswer = (questionId, answer, timeTaken) =>
  request(`/practice/questions/${questionId}/submit`, {
    method: 'POST',
    auth: true,
    body: JSON.stringify({ answer, time_taken: timeTaken }),
  })

export const showSolution = (questionId) =>
  request(`/practice/questions/${questionId}/show-solution`, {
    method: 'POST',
    auth: true,
  })

// -- dashboard --------------------------------------------------------------
export const getDashboard = () => request('/dashboard', { auth: true })

// -- MentisQ (AI tutor) --------------------------------------------------
// `context` is one of { topic_slug } / { question_id } / {} (general question).
// `opts` carries the multi-turn bits: { session_id } to continue a conversation,
// { new_chat: true } to force a fresh one.
export const askMentisQ = (content, context = {}, opts = {}) =>
  request('/mentisq/messages', {
    method: 'POST',
    auth: true,
    body: JSON.stringify({ content, ...context, ...opts }),
  })

// The general conversation the next general message would continue (with its
// turns), or null.
export const getCurrentMentisQSession = () =>
  request('/mentisq/sessions/current', { auth: true })

// Record 👍/👎 on a conversation. `helpful` is true | false | null (clear).
export const rateMentisQSession = (sessionId, helpful) =>
  request(`/mentisq/sessions/${sessionId}/helpful`, {
    method: 'POST',
    auth: true,
    body: JSON.stringify({ helpful }),
  })

// -- admin: MentisQ settings (SuperAdmin only) -------------------------
export const getMentisQSettings = () =>
  request('/admin/mentisq-settings', { auth: true })

export const updateMentisQSettings = (payload) =>
  request('/admin/mentisq-settings', {
    method: 'PUT',
    auth: true,
    body: JSON.stringify(payload),
  })
