<script setup>
import { ref } from 'vue'
import { forgotPassword } from '../api'

const email = ref('')
const sent = ref(false)
const submitting = ref(false)

async function submit() {
  submitting.value = true
  try {
    await forgotPassword(email.value)
    sent.value = true
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="auth-card">
    <h1>Reset your password</h1>
    <div v-if="sent" class="form-note">
      <p>If that email is registered, a reset link is on its way.</p>
      <RouterLink to="/login">Back to log in</RouterLink>
    </div>
    <form v-else @submit.prevent="submit">
      <div class="form-field">
        <label for="email">Email</label>
        <input id="email" v-model="email" type="email" autocomplete="email" required />
      </div>
      <button class="btn" type="submit" :disabled="submitting">Send reset link</button>
    </form>
  </section>
</template>
