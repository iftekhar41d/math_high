<script setup>
// The Learn screen: a two-pane course browser. Left rail shows the student's
// year-level Subject and its Units; the right pane shows the selected Unit's
// Topics plus the two whole-unit practice CTAs. The selected Unit lives in the
// URL (`/learn/units/:unitId`) so it is shareable and survives back/forward;
// hitting `/learn` bare auto-selects the first Unit.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as api from '../api'

const route = useRoute()
const router = useRouter()

const course = ref(null)
const loading = ref(false)
const error = ref('')

const topics = ref([])
const topicsLoading = ref(false)
const topicsError = ref('')

const units = computed(() => course.value?.units ?? [])
const selectedUnitId = computed(() => Number(route.params.unitId) || null)
const selectedUnit = computed(
  () => units.value.find((u) => u.id === selectedUnitId.value) ?? null,
)

async function loadCourse() {
  loading.value = true
  error.value = ''
  try {
    course.value = await api.getMyCourse()
    ensureUnitSelected()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// With no unit in the URL (or a stale one), land on the first unit.
function ensureUnitSelected() {
  if (units.value.length === 0) return
  const known = units.value.some((u) => u.id === selectedUnitId.value)
  if (!known) {
    router.replace({
      name: 'learn-unit',
      params: { unitId: units.value[0].id },
    })
  }
}

async function loadTopics(unitId) {
  if (!unitId) {
    topics.value = []
    return
  }
  topicsLoading.value = true
  topicsError.value = ''
  try {
    topics.value = await api.getTopics(unitId)
  } catch (e) {
    topicsError.value = e.message
  } finally {
    topicsLoading.value = false
  }
}

loadCourse()
watch(selectedUnitId, (id) => loadTopics(id), { immediate: true })
watch(units, ensureUnitSelected)
</script>

<template>
  <section class="course">
    <p v-if="loading" class="course-status">Loading…</p>
    <p v-else-if="error" class="form-error">{{ error }}</p>

    <template v-else-if="course">
      <aside class="rail">
        <p class="rail-eyebrow">{{ course.year_level.name }}</p>
        <h1 class="rail-subject">
          {{ course.subject?.title ?? 'No subject yet' }}
        </h1>

        <p v-if="units.length === 0" class="course-status">
          No units in this subject yet.
        </p>
        <ul v-else class="unit-list">
          <li v-for="unit in units" :key="unit.id">
            <RouterLink
              class="unit-link"
              :class="{ active: unit.id === selectedUnitId }"
              :to="{ name: 'learn-unit', params: { unitId: unit.id } }"
            >
              {{ unit.title }}
            </RouterLink>
          </li>
        </ul>
      </aside>

      <div class="pane">
        <template v-if="selectedUnit">
          <h2 class="pane-title">{{ selectedUnit.title }}</h2>

          <div class="unit-ctas">
            <RouterLink
              class="unit-cta"
              :to="{ name: 'learn-mixed-practice', params: { unitId: selectedUnit.id } }"
            >
              Mixed practice for this unit →
            </RouterLink>
            <RouterLink
              class="unit-cta"
              :to="{ name: 'learn-timed-quiz', params: { unitId: selectedUnit.id } }"
            >
              Start a timed quiz for this unit →
            </RouterLink>
          </div>

          <p v-if="topicsLoading" class="course-status">Loading topics…</p>
          <p v-else-if="topicsError" class="form-error">{{ topicsError }}</p>
          <p v-else-if="topics.length === 0" class="course-status">
            No published topics in this unit yet.
          </p>
          <ul v-else class="topic-list">
            <li v-for="topic in topics" :key="topic.id">
              <RouterLink
                class="topic-link"
                :to="{ name: 'learn-topic', params: { slug: topic.slug } }"
              >
                {{ topic.title }}
              </RouterLink>
            </li>
          </ul>
        </template>
        <p v-else class="course-status">Select a unit to see its topics.</p>
      </div>
    </template>
  </section>
</template>

<style scoped>
.course {
  display: grid;
  grid-template-columns: minmax(200px, 260px) 1fr;
  gap: 1.75rem;
  align-items: start;
}
.course-status {
  color: var(--color-text);
  opacity: 0.75;
}

/* -- left rail --------------------------------------------------------- */
.rail {
  border-right: 1px solid var(--color-accent);
  padding-right: 1.25rem;
}
.rail-eyebrow {
  margin: 0;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text);
  opacity: 0.6;
}
.rail-subject {
  margin: 0.15rem 0 1rem;
  font-size: 1.35rem;
  line-height: 1.2;
  color: var(--color-primary);
}
.unit-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.unit-link {
  display: block;
  padding: 0.55rem 0.7rem;
  border-radius: 6px;
  text-decoration: none;
  color: var(--color-text);
  font-size: 0.95rem;
}
.unit-link:hover {
  background: var(--color-surface);
}
.unit-link.active {
  background: var(--color-accent);
  font-weight: 700;
}

/* -- right pane ------------------------------------------------------- */
.pane {
  min-width: 0;
}
.pane-title {
  margin: 0 0 0.9rem;
  font-size: 1.4rem;
  color: var(--color-text);
}
.unit-ctas {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-bottom: 1.25rem;
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
.unit-cta:hover {
  opacity: 0.92;
}
.topic-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.topic-list li {
  border: 1px solid var(--color-accent);
  border-radius: 8px;
}
.topic-link {
  display: block;
  padding: 0.85rem 1rem;
  text-decoration: none;
  font-weight: 600;
  color: var(--color-primary);
}
.topic-link:hover {
  background: var(--color-surface);
}

@media (max-width: 760px) {
  .course {
    grid-template-columns: 1fr;
    gap: 1rem;
  }
  .rail {
    border-right: none;
    border-bottom: 1px solid var(--color-accent);
    padding-right: 0;
    padding-bottom: 1rem;
  }
  .unit-list {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 0.4rem;
  }
  .unit-link {
    border: 1px solid var(--color-accent);
  }
}
</style>
