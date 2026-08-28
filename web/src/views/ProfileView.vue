<script setup>
import { reactive, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { YEAR_LEVELS } from '../constants'

const auth = useAuthStore()
const router = useRouter()
const { user } = storeToRefs(auth)

const form = reactive({
  name: user.value?.name ?? '',
  avatar_url: user.value?.avatar_url ?? '',
  year_level: user.value?.year_level ?? 7,
})
const status = ref('')
const error = ref('')
const saving = ref(false)

async function save() {
  status.value = ''
  error.value = ''
  saving.value = true
  try {
    await auth.updateProfile({
      name: form.name,
      avatar_url: form.avatar_url || null,
      year_level: Number(form.year_level),
    })
    status.value = 'Saved.'
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

async function signOut() {
  await auth.logout()
  router.push('/login')
}

async function signOutEverywhere() {
  await auth.logoutAll()
  router.push('/login')
}
</script>

<template>
  <section class="auth-card" v-if="user">
    <h1>Your profile</h1>
    <p>Signed in as <strong>{{ user.email }}</strong></p>

    <form @submit.prevent="save">
      <div class="form-field">
        <label for="name">Display name</label>
        <input id="name" v-model="form.name" type="text" required />
      </div>
      <div class="form-field">
        <label for="avatar">Avatar URL</label>
        <input id="avatar" v-model="form.avatar_url" type="text" placeholder="/media/…" />
      </div>
      <div class="form-field">
        <label for="year">Year level</label>
        <select id="year" v-model="form.year_level">
          <option v-for="y in YEAR_LEVELS" :key="y" :value="y">Year {{ y }}</option>
        </select>
      </div>
      <p v-if="error" class="form-error">{{ error }}</p>
      <p v-if="status">{{ status }}</p>
      <button class="btn" type="submit" :disabled="saving">Save changes</button>
    </form>

    <hr />
    <div class="session-actions">
      <button class="btn btn-secondary" type="button" @click="signOut">Log out</button>
      <button class="btn btn-secondary" type="button" @click="signOutEverywhere">
        Log out of all devices
      </button>
    </div>
  </section>
</template>

<style scoped>
hr {
  border: none;
  border-top: 1px solid var(--color-accent);
  margin: 1.5rem 0 1rem;
}
.session-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}
</style>
