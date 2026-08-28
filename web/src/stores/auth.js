import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import * as api from '../api'

// Holds the signed-in student. The access token is kept in a plain module ref
// (never persisted); the refresh cookie is what survives a reload, so
// `restore()` runs once at startup to trade it for a fresh access token.
export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const ready = ref(false) // initial restore() attempt has completed
  let refreshInFlight = null

  const isAuthenticated = computed(() => user.value !== null)

  function setSession({ access_token, user: u }) {
    api.setAccessToken(access_token)
    user.value = u
  }

  function clearSession() {
    api.setAccessToken(null)
    user.value = null
  }

  async function restore() {
    try {
      setSession(await api.refreshSession())
    } catch {
      clearSession()
    } finally {
      ready.value = true
    }
  }

  // Registered with the api layer so a 401 on any authenticated call gets one
  // transparent refresh. Concurrent callers share the same in-flight promise.
  async function refresh() {
    if (!refreshInFlight) {
      refreshInFlight = api
        .refreshSession()
        .then((session) => {
          setSession(session)
          return true
        })
        .catch(() => {
          clearSession()
          return false
        })
        .finally(() => {
          refreshInFlight = null
        })
    }
    return refreshInFlight
  }
  api.setRefreshHandler(refresh)

  async function login(email, password) {
    setSession(await api.login(email, password))
  }

  async function logout() {
    try {
      await api.logout()
    } finally {
      clearSession()
    }
  }

  async function logoutAll() {
    try {
      await api.logoutAll()
    } finally {
      clearSession()
    }
  }

  async function refreshProfile() {
    user.value = await api.getProfile()
  }

  async function updateProfile(payload) {
    user.value = await api.updateProfile(payload)
  }

  return {
    user,
    ready,
    isAuthenticated,
    restore,
    login,
    logout,
    logoutAll,
    refreshProfile,
    updateProfile,
  }
})
