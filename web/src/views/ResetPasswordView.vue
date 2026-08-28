<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { resetPassword } from '../api'

const route = useRoute()
const password = ref('')
const error = ref('')
const done = ref(false)
const submitting = ref(false)

async function submit() {
  error.value = ''
  const token = route.query.token
  if (!token) {
    error.value = 'This reset link is missing its token.'
    return
  }
  submitting.value = true
  try {
    await resetPassword(token, password.value)
    done.value = true
  } catch (e) {
    error.value =
      e.status === 400
        ? 'That reset link is invalid or has expired. Request a new one.'
        : e.message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="auth-card">
    <h1>Set a new password</h1>
    <div v-if="done" class="form-note">
      <p>Password updated. Log in with your new password.</p>
      <RouterLink to="/login">Go to log in</RouterLink>
    </div>
    <form v-else @submit.prevent="submit">
      <div class="form-field">
        <label for="password">New password</label>
        <input
          id="password"
          v-model="password"
          type="password"
          autocomplete="new-password"
          minlength="8"
          required
        />
      </div>
      <p v-if="error" class="form-error">{{ error }}</p>
      <button class="btn" type="submit" :disabled="submitting">Update password</button>
    </form>
  </section>
</template>
