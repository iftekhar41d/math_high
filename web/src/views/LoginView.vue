<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { resendVerification } from '../api'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const email = ref('')
const password = ref('')
const error = ref('')
const unverified = ref(false)
const resent = ref(false)
const submitting = ref(false)

async function submit() {
  error.value = ''
  unverified.value = false
  resent.value = false
  submitting.value = true
  try {
    await auth.login(email.value, password.value)
    router.push(route.query.redirect || '/learn')
  } catch (e) {
    if (e.status === 403) {
      // /auth/login only 403s when the email isn't verified yet.
      unverified.value = true
    } else if (e.status === 429) {
      error.value = 'Too many failed attempts. Please wait a few minutes and try again.'
    } else if (e.status === 401) {
      error.value = 'Incorrect email or password.'
    } else {
      error.value = e.message
    }
  } finally {
    submitting.value = false
  }
}

async function resend() {
  await resendVerification(email.value)
  resent.value = true
}
</script>

<template>
  <section class="auth-card">
    <h1>Log in</h1>
    <form @submit.prevent="submit">
      <div class="form-field">
        <label for="email">Email</label>
        <input id="email" v-model="email" type="email" autocomplete="email" required />
      </div>
      <div class="form-field">
        <label for="password">Password</label>
        <input
          id="password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
        />
      </div>
      <p v-if="error" class="form-error">{{ error }}</p>
      <div v-if="unverified" class="form-note">
        <p>Your email isn't verified yet.</p>
        <button v-if="!resent" type="button" class="btn btn-secondary" @click="resend">
          Resend verification email
        </button>
        <p v-else>Sent — check your inbox.</p>
      </div>
      <button class="btn" type="submit" :disabled="submitting">Log in</button>
    </form>
    <p>
      <RouterLink to="/forgot-password">Forgot your password?</RouterLink>
    </p>
    <p>New here? <RouterLink to="/register">Create an account</RouterLink></p>
  </section>
</template>
