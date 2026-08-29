<script setup>
// Topic practice: work through the Topic's questions, submit answers for
// server-side grading, get immediate feedback, and reveal the worked solution
// (shown automatically after the first submission, or on request). The correct
// answer is never in the payload — grading happens on the API.
import { reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import * as api from '../api'
import { renderLecture } from '../lib/lecture'
import AskMentisQ from '../components/AskMentisQ.vue'

const route = useRoute()

const session = ref(null)
const loading = ref(false)
const error = ref('')
const notFound = ref(false)

// Per-question interaction state, keyed by question id.
const qs = reactive({})

function resetState(questions) {
  for (const k of Object.keys(qs)) delete qs[k]
  for (const q of questions) {
    qs[q.id] = {
      single: '',
      multi: [],
      numeric: '',
      startedAt: Date.now(),
      submitting: false,
      result: null, // { is_correct, attempt_no, worked_solution }
      solution: '', // worked solution text, once available
      err: '',
    }
  }
}

async function load() {
  loading.value = true
  error.value = ''
  notFound.value = false
  session.value = null
  try {
    const data = await api.startPractice(route.params.slug)
    session.value = data
    resetState(data.questions)
  } catch (e) {
    if (e.status === 404) notFound.value = true
    else error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(() => route.params.slug, load, { immediate: true })

const render = (text) => renderLecture(text)

function answerFor(q) {
  const s = qs[q.id]
  if (q.type === 'mcq_single') return s.single
  if (q.type === 'mcq_multi') return [...s.multi]
  return s.numeric === '' ? null : Number(s.numeric)
}

function canSubmit(q) {
  const s = qs[q.id]
  if (s.submitting) return false
  if (q.type === 'mcq_single') return s.single !== ''
  if (q.type === 'mcq_multi') return s.multi.length > 0
  return s.numeric !== '' && !Number.isNaN(Number(s.numeric))
}

async function submit(q) {
  const s = qs[q.id]
  s.err = ''
  s.submitting = true
  const elapsed = Math.max(1, Math.round((Date.now() - s.startedAt) / 1000))
  try {
    const res = await api.submitAnswer(q.id, answerFor(q), elapsed)
    s.result = res
    s.solution = res.worked_solution
  } catch (e) {
    s.err = e.message
  } finally {
    s.submitting = false
  }
}

async function reveal(q) {
  const s = qs[q.id]
  s.err = ''
  try {
    const res = await api.showSolution(q.id)
    s.solution = res.worked_solution
  } catch (e) {
    s.err = e.message
  }
}
</script>

<template>
  <section class="practice">
    <nav class="crumbs">
      <button type="button" class="link-button" @click="$router.back()">← Back</button>
      <RouterLink :to="{ name: 'learn' }">All year levels</RouterLink>
    </nav>

    <p v-if="loading">Loading…</p>
    <p v-else-if="error" class="form-error">{{ error }}</p>
    <p v-else-if="notFound" class="form-error">
      That topic isn’t available.
      <RouterLink :to="{ name: 'learn' }">Browse the course</RouterLink>.
    </p>

    <template v-else-if="session">
      <h1>Practice: {{ session.topic.title }}</h1>
      <p v-if="session.questions.length === 0">
        This topic has no practice questions yet.
      </p>

      <ol class="questions">
        <li v-for="(q, i) in session.questions" :key="q.id" class="qcard">
          <div class="qhead">
            <span class="qnum">Question {{ i + 1 }}</span>
            <span class="difficulty" :data-level="q.difficulty">{{ q.difficulty }}</span>
          </div>

          <div class="qbody lecture-body" v-html="render(q.body)" />

          <!-- single-select -->
          <fieldset v-if="q.type === 'mcq_single'" class="options">
            <label v-for="opt in q.options" :key="opt.id" class="option">
              <input type="radio" :name="`q-${q.id}`" :value="opt.id" v-model="qs[q.id].single" />
              <span v-html="render(opt.text)" />
            </label>
          </fieldset>

          <!-- multi-select -->
          <fieldset v-else-if="q.type === 'mcq_multi'" class="options">
            <p class="hint">Select all that apply.</p>
            <label v-for="opt in q.options" :key="opt.id" class="option">
              <input type="checkbox" :value="opt.id" v-model="qs[q.id].multi" />
              <span v-html="render(opt.text)" />
            </label>
          </fieldset>

          <!-- numeric -->
          <div v-else class="numeric">
            <label :for="`num-${q.id}`">Your answer</label>
            <input
              :id="`num-${q.id}`"
              type="number"
              inputmode="decimal"
              step="any"
              v-model="qs[q.id].numeric"
              @keyup.enter="canSubmit(q) && submit(q)"
            />
          </div>

          <div class="actions">
            <button class="btn" :disabled="!canSubmit(q)" @click="submit(q)">
              {{ qs[q.id].submitting ? 'Checking…' : qs[q.id].result ? 'Submit again' : 'Submit' }}
            </button>
            <button
              v-if="!qs[q.id].solution"
              class="btn btn-secondary"
              type="button"
              @click="reveal(q)"
            >
              Show solution
            </button>
          </div>

          <p v-if="qs[q.id].err" class="form-error">{{ qs[q.id].err }}</p>

          <p
            v-if="qs[q.id].result"
            class="verdict"
            :class="qs[q.id].result.is_correct ? 'correct' : 'incorrect'"
          >
            {{ qs[q.id].result.is_correct ? 'Correct' : 'Not quite' }}
            <span class="attempt">· attempt {{ qs[q.id].result.attempt_no }}</span>
          </p>

          <div v-if="qs[q.id].solution" class="solution">
            <h3>Worked solution</h3>
            <div class="lecture-body" v-html="render(qs[q.id].solution)" />
          </div>

          <AskMentisQ :question-id="q.id" />
        </li>
      </ol>
    </template>
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
.link-button {
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  color: var(--color-primary);
  cursor: pointer;
}
h1 {
  color: var(--color-primary);
  font-size: 1.5rem;
  margin: 0.2rem 0 1.25rem;
}
.questions {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
.qcard {
  border: 1px solid var(--color-accent);
  border-radius: 10px;
  padding: 1rem 1.1rem;
}
.qhead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.4rem;
}
.qnum {
  font-weight: 700;
  color: var(--color-primary);
  font-size: 0.9rem;
}
.difficulty {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  background: var(--color-accent);
  color: var(--color-text);
}
.difficulty[data-level='hard'] {
  background: var(--color-primary);
  color: var(--color-bg);
}
.qbody {
  margin-bottom: 0.75rem;
}
.options {
  border: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.hint,
.options .hint {
  font-size: 0.85rem;
  margin: 0 0 0.2rem;
  font-weight: 600;
}
.option {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--color-accent);
  border-radius: 8px;
  cursor: pointer;
}
.option input {
  margin-top: 0.2rem;
}
.numeric {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.numeric label {
  font-weight: 600;
  font-size: 0.9rem;
}
.numeric input {
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--color-accent);
  border-radius: 6px;
  font: inherit;
  max-width: 12rem;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-top: 0.9rem;
}
.verdict {
  font-weight: 700;
  margin: 0.9rem 0 0;
}
.verdict.correct {
  color: var(--color-primary);
}
.verdict .attempt {
  font-weight: 400;
  color: var(--color-text);
  font-size: 0.85rem;
}
.solution {
  margin-top: 0.9rem;
  padding: 0.85rem 1rem;
  background: var(--color-accent);
  border-radius: 8px;
}
.solution h3 {
  margin: 0 0 0.4rem;
  font-size: 0.95rem;
  color: var(--color-primary);
}

/* Phone: tighten the cards and let the buttons fill the row so they're
   comfortable tap targets. */
@media (max-width: 480px) {
  h1 {
    font-size: 1.3rem;
  }
  .qcard {
    padding: 0.85rem 0.9rem;
  }
  .actions {
    flex-direction: column;
  }
  .actions .btn {
    width: 100%;
  }
  .numeric input {
    max-width: none;
  }
}
</style>
