<script setup>
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useMetaStore } from '../stores/meta'

const store = useMetaStore()
const { data, loading, error } = storeToRefs(store)

onMounted(store.load)
</script>

<template>
  <section>
    <h1>MentisQ</h1>
    <p class="tagline">Structured NSW high-school maths — lessons, practice, and a guided AI tutor.</p>

    <div class="status-card">
      <h2>Backend status</h2>
      <p v-if="loading">Checking…</p>
      <p v-else-if="error" class="error">Can't reach the API: {{ error }}</p>
      <dl v-else-if="data">
        <dt>App</dt>
        <dd>{{ data.app }}</dd>
        <dt>Environment</dt>
        <dd>{{ data.environment }}</dd>
        <dt>Database</dt>
        <dd>{{ data.database }}</dd>
        <dt>Server time</dt>
        <dd>{{ data.server_time }}</dd>
      </dl>
    </div>
  </section>
</template>

<style scoped>
h1 {
  color: var(--color-primary);
  margin-bottom: 0.25rem;
}
.tagline {
  margin-top: 0;
  color: var(--color-text);
}
.status-card {
  margin-top: 1.5rem;
  padding: 1rem 1.25rem;
  background: var(--color-accent);
  border-radius: 8px;
}
.status-card h2 {
  margin-top: 0;
  font-size: 1rem;
}
dl {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.35rem 1rem;
  margin: 0;
}
dt {
  font-weight: 600;
}
dd {
  margin: 0;
}
.error {
  color: var(--color-text);
  font-weight: 600;
}
</style>
