import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getMeta } from '../api'

// Holds the result of the one real backend round trip the app shell makes.
export const useMetaStore = defineStore('meta', () => {
  const data = ref(null)
  const loading = ref(false)
  const error = ref('')

  async function load() {
    loading.value = true
    error.value = ''
    try {
      data.value = await getMeta()
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  return { data, loading, error, load }
})
