<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { verifyEmail } from '../api'

const route = useRoute()
const state = ref('working') // working | ok | bad

onMounted(async () => {
  const token = route.query.token
  if (!token) {
    state.value = 'bad'
    return
  }
  try {
    await verifyEmail(token)
    state.value = 'ok'
  } catch {
    state.value = 'bad'
  }
})
</script>

<template>
  <section class="auth-card">
    <h1>Email verification</h1>
    <p v-if="state === 'working'">Verifying…</p>
    <div v-else-if="state === 'ok'" class="form-note">
      <p>Your email is verified. You can log in now.</p>
      <RouterLink to="/login">Go to log in</RouterLink>
    </div>
    <div v-else class="form-note">
      <p>That verification link is invalid or has expired.</p>
      <RouterLink to="/login">Log in</RouterLink> to request a fresh one.
    </div>
  </section>
</template>
