<script setup>
import { ref } from 'vue'
import { register } from '../api'
import { YEAR_LEVELS } from '../constants'

const form = ref({ email: '', password: '', name: '', year_level: 7 })
const error = ref('')
const done = ref(false)
const submitting = ref(false)

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    await register({ ...form.value, year_level: Number(form.value.year_level) })
    done.value = true
  } catch (e) {
    if (e.status === 409) {
      error.value = 'That email is already registered. Try logging in.'
    } else if (e.status === 422) {
      error.value = 'Please check your details — the password must be at least 8 characters.'
    } else {
      error.value = e.message
    }
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="auth-card">
    <h1>Create your account</h1>

    <div v-if="done" class="form-note">
      <p>
        Almost there — we've emailed <strong>{{ form.email }}</strong> a verification
        link. Follow it, then log in.
      </p>
      <RouterLink to="/login">Go to log in</RouterLink>
    </div>

    <form v-else @submit.prevent="submit">
      <div class="form-field">
        <label for="name">Name</label>
        <input id="name" v-model="form.name" type="text" autocomplete="name" required />
      </div>
      <div class="form-field">
        <label for="email">Email</label>
        <input id="email" v-model="form.email" type="email" autocomplete="email" required />
      </div>
      <div class="form-field">
        <label for="password">Password</label>
        <input
          id="password"
          v-model="form.password"
          type="password"
          autocomplete="new-password"
          minlength="8"
          required
        />
      </div>
      <div class="form-field">
        <label for="year">Year level</label>
        <select id="year" v-model="form.year_level">
          <option v-for="y in YEAR_LEVELS" :key="y" :value="y">Year {{ y }}</option>
        </select>
      </div>
      <p v-if="error" class="form-error">{{ error }}</p>
      <button class="btn" type="submit" :disabled="submitting">Register</button>
    </form>

    <p v-if="!done">Already have an account? <RouterLink to="/login">Log in</RouterLink></p>
  </section>
</template>
