<script setup>
// The student's recent activity: recent question attempts, percentage correct
// per Topic, and how much they've used lectures and MentisQ lately. Everything
// is computed on read by the API (`GET /api/dashboard`); this view only renders.
import { onMounted, ref } from 'vue'
import * as api from '../api'

const dash = ref(null)
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    dash.value = await api.getDashboard()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)

const dateFmt = new Intl.DateTimeFormat(undefined, {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})
const when = (iso) => dateFmt.format(new Date(iso))
</script>

<template>
  <section class="dashboard">
    <h1>Your dashboard</h1>

    <p v-if="loading">Loading…</p>
    <p v-else-if="error" class="form-error">{{ error }}</p>

    <template v-else-if="dash">
      <!-- activity over the recent window -->
      <h2>Last {{ dash.activity.window_days }} days</h2>
      <ul class="stats">
        <li class="stat">
          <span class="stat-value">{{ dash.activity.topics_viewed }}</span>
          <span class="stat-label">
            {{ dash.activity.topics_viewed === 1 ? 'topic' : 'topics' }} opened
          </span>
        </li>
        <li class="stat">
          <span class="stat-value">{{ dash.activity.topic_views }}</span>
          <span class="stat-label">lecture views</span>
        </li>
        <li class="stat">
          <span class="stat-value">{{ dash.activity.mentisq_messages }}</span>
          <span class="stat-label">MentisQ messages</span>
        </li>
      </ul>

      <!-- per-Topic percentage correct -->
      <h2>How you're doing per topic</h2>
      <p v-if="dash.topic_performance.length === 0" class="muted">
        Answer some practice questions and your accuracy per topic shows up here.
      </p>
      <ul v-else class="topics">
        <li v-for="t in dash.topic_performance" :key="t.topic_slug" class="topic">
          <div class="topic-head">
            <RouterLink
              :to="{ name: 'learn-topic', params: { slug: t.topic_slug } }"
            >
              {{ t.topic_title }}
            </RouterLink>
            <span class="pct">{{ t.percent_correct }}%</span>
          </div>
          <div
            class="bar"
            role="img"
            :aria-label="`${t.correct} of ${t.attempts} correct`"
          >
            <div class="bar-fill" :style="{ width: t.percent_correct + '%' }" />
          </div>
          <span class="topic-sub">{{ t.correct }} / {{ t.attempts }} correct</span>
        </li>
      </ul>

      <!-- recent attempts -->
      <h2>Recent attempts</h2>
      <p v-if="dash.recent_attempts.length === 0" class="muted">
        You haven't attempted any practice questions yet.
      </p>
      <ul v-else class="attempts">
        <li
          v-for="a in dash.recent_attempts"
          :key="a.id"
          class="attempt"
          :class="a.is_correct ? 'correct' : 'incorrect'"
        >
          <span class="verdict">{{ a.is_correct ? 'Correct' : 'Not quite' }}</span>
          <div class="attempt-body">
            <RouterLink
              :to="{ name: 'learn-topic', params: { slug: a.topic_slug } }"
              class="attempt-topic"
            >
              {{ a.topic_title }}
            </RouterLink>
            <span class="difficulty" :data-level="a.difficulty">
              {{ a.difficulty }}
            </span>
            <span class="attempt-meta">
              attempt {{ a.attempt_no }}
              <template v-if="a.solution_viewed"> · viewed solution</template>
              · {{ when(a.created_at) }}
            </span>
          </div>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
h1 {
  color: var(--color-primary);
  font-size: 1.5rem;
  margin: 0.2rem 0 1rem;
}
h2 {
  color: var(--color-primary);
  font-size: 1rem;
  margin: 1.75rem 0 0.75rem;
}
.muted {
  color: var(--color-text);
  opacity: 0.8;
  font-size: 0.95rem;
}
ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

/* activity stat cards */
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: 0.75rem;
}
.stat {
  border: 1px solid var(--color-accent);
  border-radius: 10px;
  padding: 0.9rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.stat-value {
  font-size: 1.6rem;
  font-weight: 700;
  color: var(--color-primary);
  line-height: 1;
}
.stat-label {
  font-size: 0.85rem;
}

/* per-topic bars */
.topics {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}
.topic {
  border: 1px solid var(--color-accent);
  border-radius: 10px;
  padding: 0.8rem 1rem;
}
.topic-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.75rem;
}
.topic-head a {
  font-weight: 600;
  text-decoration: none;
}
.pct {
  font-weight: 700;
  color: var(--color-primary);
}
.bar {
  margin: 0.5rem 0 0.3rem;
  height: 0.5rem;
  border-radius: 999px;
  background: var(--color-accent);
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  background: var(--color-primary);
}
.topic-sub {
  font-size: 0.8rem;
  opacity: 0.8;
}

/* recent attempts */
.attempts {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.attempt {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  border: 1px solid var(--color-accent);
  border-left: 4px solid var(--color-accent);
  border-radius: 8px;
  padding: 0.65rem 0.85rem;
}
.attempt.correct {
  border-left-color: var(--color-primary);
}
.attempt.incorrect {
  border-left-color: var(--color-text);
}
.verdict {
  font-weight: 700;
  font-size: 0.85rem;
  white-space: nowrap;
}
.attempt-body {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.4rem 0.6rem;
}
.attempt-topic {
  font-weight: 600;
  text-decoration: none;
}
.attempt-meta {
  font-size: 0.8rem;
  opacity: 0.8;
  width: 100%;
}
.difficulty {
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  background: var(--color-accent);
  color: var(--color-text);
}
.difficulty[data-level='hard'] {
  background: var(--color-primary);
  color: var(--color-bg);
}

@media (max-width: 480px) {
  h1 {
    font-size: 1.3rem;
  }
  .stat-value {
    font-size: 1.4rem;
  }
}
</style>
