<script setup>
// SuperAdmin screen: read and update the MentisQ model name and the usage caps.
// Non-SuperAdmin callers get a 403 from the API, shown here as a plain notice.
import { onMounted, reactive, ref } from 'vue'
import * as api from '../api'

const loading = ref(true)
const forbidden = ref(false)
const error = ref('')
const status = ref('')
const saving = ref(false)

const form = reactive({
  model_name: '',
  daily_message_cap: 0,
  per_student_monthly_cap_usd: 0,
  global_monthly_cap_usd: '', // '' = no global ceiling
})

function fill(settings) {
  form.model_name = settings.model_name
  form.daily_message_cap = settings.daily_message_cap
  form.per_student_monthly_cap_usd = settings.per_student_monthly_cap_usd
  form.global_monthly_cap_usd =
    settings.global_monthly_cap_usd == null ? '' : settings.global_monthly_cap_usd
}

onMounted(async () => {
  try {
    fill(await api.getMentisQSettings())
  } catch (e) {
    if (e.status === 403) forbidden.value = true
    else error.value = e.message
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  status.value = ''
  error.value = ''
  try {
    const payload = {
      model_name: form.model_name,
      daily_message_cap: Number(form.daily_message_cap),
      per_student_monthly_cap_usd: Number(form.per_student_monthly_cap_usd),
      global_monthly_cap_usd:
        form.global_monthly_cap_usd === '' ||
        form.global_monthly_cap_usd === null
          ? null
          : Number(form.global_monthly_cap_usd),
    }
    fill(await api.updateMentisQSettings(payload))
    status.value = 'Saved.'
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="admin">
    <h1>MentisQ settings</h1>

    <p v-if="loading">Loading…</p>
    <p v-else-if="forbidden" class="form-error">
      This page is for SuperAdmins only.
    </p>

    <form v-else @submit.prevent="save">
      <div class="form-field">
        <label for="model">Model name</label>
        <input id="model" v-model="form.model_name" type="text" required />
        <p class="hint">OpenRouter model id, e.g. <code>openai/gpt-4o-mini</code>.</p>
      </div>

      <div class="form-field">
        <label for="daily">Daily message cap (per student)</label>
        <input
          id="daily"
          v-model="form.daily_message_cap"
          type="number"
          min="0"
          required
        />
      </div>

      <div class="form-field">
        <label for="perstudent">Monthly spend cap per student (USD)</label>
        <input
          id="perstudent"
          v-model="form.per_student_monthly_cap_usd"
          type="number"
          min="0"
          step="0.01"
          required
        />
      </div>

      <div class="form-field">
        <label for="global">Global monthly spend cap (USD)</label>
        <input
          id="global"
          v-model="form.global_monthly_cap_usd"
          type="number"
          min="0"
          step="0.01"
          placeholder="Leave blank for no global ceiling"
        />
      </div>

      <button class="btn" :disabled="saving" type="submit">
        {{ saving ? 'Saving…' : 'Save' }}
      </button>
      <p v-if="status" class="save-status">{{ status }}</p>
      <p v-if="error" class="form-error">{{ error }}</p>
    </form>
  </section>
</template>

<style scoped>
/* `.form-field` and its label/input rules come from the global stylesheet. */
.admin h1 {
  color: var(--color-primary);
  font-size: 1.5rem;
  margin: 0.2rem 0 1rem;
}
.form-field input {
  max-width: 22rem;
}
.hint {
  font-size: 0.8rem;
  margin: 0;
}
.save-status {
  color: var(--color-primary);
  font-weight: 600;
}
</style>
