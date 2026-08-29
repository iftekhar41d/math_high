<script setup>
// Drives every list level of the course tree (year levels → subjects → units
// → topics). Which level it shows is read from the route name; each row links
// one level deeper, and the last level links into the lecture reader.
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import * as api from '../api'

const route = useRoute()

const LEVELS = {
  learn: {
    heading: 'Year levels',
    empty: 'No year levels are available yet.',
    load: () => api.getYearLevels(),
    label: (item) => item.name,
    to: (item) => ({ name: 'learn-year', params: { yearLevelId: item.id } }),
  },
  'learn-year': {
    heading: 'Subjects',
    empty: 'No subjects in this year level yet.',
    load: () => api.getSubjects(route.params.yearLevelId),
    label: (item) => item.title,
    to: (item) => ({ name: 'learn-subject', params: { subjectId: item.id } }),
  },
  'learn-subject': {
    heading: 'Units',
    empty: 'No units in this subject yet.',
    load: () => api.getUnits(route.params.subjectId),
    label: (item) => item.title,
    to: (item) => ({ name: 'learn-unit', params: { unitId: item.id } }),
  },
  'learn-unit': {
    heading: 'Topics',
    empty: 'No published topics in this unit yet.',
    load: () => api.getTopics(route.params.unitId),
    label: (item) => item.title,
    to: (item) => ({ name: 'learn-topic', params: { slug: item.slug } }),
  },
}

const level = computed(() => LEVELS[route.name] ?? LEVELS.learn)
const items = ref([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  items.value = []
  try {
    items.value = await level.value.load()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(() => route.fullPath, load, { immediate: true })
</script>

<template>
  <section class="browse">
    <nav class="crumbs">
      <RouterLink :to="{ name: 'learn' }">All year levels</RouterLink>
      <button
        v-if="route.name !== 'learn'"
        type="button"
        class="link-button"
        @click="$router.back()"
      >
        ← Back
      </button>
    </nav>

    <h1>{{ level.heading }}</h1>

    <div v-if="route.name === 'learn-unit'" class="unit-ctas">
      <RouterLink
        class="unit-cta"
        :to="{ name: 'learn-mixed-practice', params: { unitId: route.params.unitId } }"
      >
        Mixed practice for this unit →
      </RouterLink>
      <RouterLink
        class="unit-cta"
        :to="{ name: 'learn-timed-quiz', params: { unitId: route.params.unitId } }"
      >
        Start a timed quiz for this unit →
      </RouterLink>
    </div>

    <p v-if="loading">Loading…</p>
    <p v-else-if="error" class="form-error">{{ error }}</p>
    <p v-else-if="items.length === 0">{{ level.empty }}</p>
    <ul v-else class="tree-list">
      <li v-for="item in items" :key="item.id">
        <RouterLink :to="level.to(item)">{{ level.label(item) }}</RouterLink>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.crumbs {
  display: flex;
  gap: 1rem;
  align-items: center;
  font-size: 0.9rem;
  margin-bottom: 0.5rem;
}
h1 {
  color: var(--color-primary);
  font-size: 1.4rem;
}
.tree-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.tree-list li {
  border: 1px solid var(--color-accent);
  border-radius: 8px;
}
.tree-list a {
  display: block;
  padding: 0.85rem 1rem;
  text-decoration: none;
  font-weight: 600;
}
.tree-list a.router-link-active {
  text-decoration: underline;
}
.unit-ctas {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin: 0.25rem 0 1rem;
}
.unit-cta {
  display: inline-block;
  padding: 0.6rem 0.9rem;
  border: 1px solid var(--color-primary);
  border-radius: 8px;
  background: var(--color-primary);
  color: var(--color-bg);
  font-weight: 600;
  font-size: 0.9rem;
  text-decoration: none;
}
.link-button {
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  color: var(--color-primary);
  cursor: pointer;
}
</style>
