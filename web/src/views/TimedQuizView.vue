<script setup>
// Timed quiz over a Unit: a frozen question set with a countdown. While the
// quiz is open the API withholds correctness and worked solutions — answers are
// just recorded. On submit (button, or the countdown hitting zero) the review
// screen shows the score and every question's worked solution. Retake as often
// as you like — each visit that isn't resuming a `?session=` starts a new run.
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as api from '../api'
import { renderLecture } from '../lib/lecture'
import AskMentisQ from '../components/AskMentisQ.vue'

const route = useRoute()
const router = useRouter()

const loading = ref(true)
const error = ref('')
const session = ref(null) // TimedSessionOut while open
const review = ref(null) // SessionReviewOut once submitted
const remaining = ref(0)
const submitting = ref(false)
let ticker = null

// Per-question interaction state, keyed by question id.
const qs = reactive({})

const render = (text) => renderLecture(text)

const clock = computed(() => {
  const s = Math.max(0, remaining.value)
  const mm = String(Math.floor(s / 60)).padStart(2, '0')
  const ss = String(s % 60).padStart(2, '0')
  return `${mm}:${ss}`
})

function freshQuestionState(q) {
  const parts = {}
  for (const p of q.parts || []) {
    parts[p.id] = { single: '', multi: [], numeric: '', symbolic: '' }
  }
  return {
    single: '',
    multi: [],
    numeric: '',
    symbolic: '',
    parts,
    startedAt: Date.now(),
    submitting: false,
    recorded: false,
    recordedLate: false,
    err: '',
  }
}

function applyStoredAnswer(q, s, ans) {
  if (ans == null) return
  if (q.type === 'mcq_single' || q.type === 'symbolic') {
    s[q.type === 'symbolic' ? 'symbolic' : 'single'] = String(ans)
  } else if (q.type === 'mcq_multi') {
    s.multi = Array.isArray(ans) ? [...ans] : []
  } else if (q.type === 'numeric') {
    s.numeric = String(ans)
  } else if (q.type === 'multi_part' && typeof ans === 'object') {
    for (const p of q.parts || []) {
      const pa = ans[p.id]
      if (pa == null) continue
      const ps = s.parts[p.id]
      if (p.type === 'mcq_single') ps.single = String(pa)
      else if (p.type === 'symbolic') ps.symbolic = String(pa)
      else if (p.type === 'mcq_multi') ps.multi = Array.isArray(pa) ? [...pa] : []
      else ps.numeric = String(pa)
    }
  }
}

function hydrate(data) {
  session.value = data
  review.value = data.review || null
  remaining.value = data.remaining_seconds || 0
  for (const k of Object.keys(qs)) delete qs[k]
  for (const q of data.questions || []) qs[q.id] = freshQuestionState(q)
  for (const a of data.answers || []) {
    if (qs[a.question_id]) {
      applyStoredAnswer(
        data.questions.find((q) => q.id === a.question_id),
        qs[a.question_id],
        a.submitted_answer,
      )
      qs[a.question_id].recorded = true
      qs[a.question_id].recordedLate = a.after_time_limit
    }
  }
  if (!review.value) startTicker()
}

function startTicker() {
  stopTicker()
  ticker = setInterval(() => {
    remaining.value = Math.max(0, remaining.value - 1)
    if (remaining.value === 0) {
      stopTicker()
      submitQuiz()
    }
  }, 1000)
}

function stopTicker() {
  if (ticker) {
    clearInterval(ticker)
    ticker = null
  }
}

onBeforeUnmount(stopTicker)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const existing = route.query.session
    if (existing) {
      hydrate(await api.getPracticeSession(existing))
    } else {
      const data = await api.startTimedQuiz(route.params.unitId)
      // Keep the id in the URL so a reload resumes rather than restarting.
      await router.replace({
        name: 'learn-timed-quiz',
        params: route.params,
        query: { session: data.session_id },
      })
      hydrate(data)
    }
  } catch (e) {
    error.value = e.message || 'Could not start the quiz.'
  } finally {
    loading.value = false
  }
}

load()

function buildPartAnswer(part, ps) {
  if (part.type === 'mcq_single') return ps.single
  if (part.type === 'mcq_multi') return [...ps.multi]
  if (part.type === 'symbolic') return ps.symbolic
  return ps.numeric === '' ? null : Number(ps.numeric)
}

function buildAnswer(q, s) {
  if (q.type === 'mcq_single') return s.single
  if (q.type === 'mcq_multi') return [...s.multi]
  if (q.type === 'symbolic') return s.symbolic
  if (q.type === 'multi_part') {
    const out = {}
    for (const p of q.parts || []) out[p.id] = buildPartAnswer(p, s.parts[p.id])
    return out
  }
  return s.numeric === '' ? null : Number(s.numeric)
}

async function recordAnswer(q) {
  const s = qs[q.id]
  s.err = ''
  s.submitting = true
  const elapsed = Math.max(1, Math.round((Date.now() - s.startedAt) / 1000))
  try {
    const res = await api.submitAnswer(q.id, buildAnswer(q, s), elapsed)
    s.recorded = true
    s.recordedLate = !!res.after_time_limit
  } catch (e) {
    s.err = e.message || 'Could not record that answer.'
  } finally {
    s.submitting = false
  }
}

async function submitQuiz() {
  if (submitting.value || review.value) return
  submitting.value = true
  stopTicker()
  try {
    review.value = await api.submitPracticeSession(
      session.value.session_id,
    )
  } catch (e) {
    error.value = e.message || 'Could not submit the quiz.'
    submitting.value = false
  }
}

const scorePercent = computed(() =>
  review.value ? Math.round(review.value.score * 1000) / 10 : 0,
)

function answerText(val) {
  if (val == null || val === '') return '(no answer)'
  if (Array.isArray(val)) return val.join(', ')
  if (typeof val === 'object') {
    return Object.entries(val)
      .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v ?? '—'}`)
      .join('; ')
  }
  return String(val)
}

function verdict(q) {
  if (q.is_correct === true) return 'correct'
  if (q.is_correct === false) return 'incorrect'
  return 'unanswered'
}
</script>

<template>
  <section class="timed">
    <nav class="crumbs">
      <button type="button" class="link-button" @click="$router.back()">← Back</button>
      <RouterLink :to="{ name: 'learn' }">All year levels</RouterLink>
    </nav>

    <p v-if="loading">Starting the quiz…</p>
    <p v-else-if="error" class="form-error">{{ error }}</p>

    <!-- review -->
    <template v-else-if="review">
      <h1>Quiz review</h1>
      <div class="scoreline">
        <span class="score">{{ scorePercent }}%</span>
        <span class="score-detail">
          {{ review.questions.filter((q) => q.is_correct === true).length }}
          / {{ review.question_count }} correct
        </span>
      </div>

      <ol class="questions">
        <li
          v-for="(q, i) in review.questions"
          :key="q.question.id"
          class="qcard"
          :class="verdict(q)"
        >
          <div class="qhead">
            <span class="qnum">Question {{ i + 1 }}</span>
            <span class="verdict-tag" :data-v="verdict(q)">
              {{ verdict(q) === 'correct' ? 'Correct' : verdict(q) === 'incorrect' ? 'Not quite' : 'Unanswered' }}
            </span>
          </div>
          <div class="qbody lecture-body" v-html="render(q.question.body)" />
          <p class="your-answer">
            Your answer: <strong>{{ answerText(q.submitted_answer) }}</strong>
            <span v-if="q.after_time_limit" class="late"> · recorded after time</span>
          </p>
          <div class="solution">
            <h3>Worked solution</h3>
            <div class="lecture-body" v-html="render(q.worked_solution)" />
          </div>
          <AskMentisQ :question-id="q.question.id" />
        </li>
      </ol>

      <RouterLink class="btn" :to="{ name: 'learn-timed-quiz', params: route.params }">
        Retake
      </RouterLink>
    </template>

    <!-- open quiz -->
    <template v-else-if="session">
      <div class="quiz-head">
        <h1>Timed quiz: {{ session.unit.title }}</h1>
        <div class="countdown" :class="{ low: remaining <= 30 }" aria-live="polite">
          {{ clock }}
        </div>
      </div>
      <p class="lead">
        No feedback until you submit. Unanswered questions are marked incorrect.
        Answers still sent after the timer runs out are kept, and flagged.
      </p>

      <ol class="questions">
        <li v-for="(q, i) in session.questions" :key="q.id" class="qcard">
          <div class="qhead">
            <span class="qnum">Question {{ i + 1 }}</span>
            <span class="difficulty" :data-level="q.difficulty">{{ q.difficulty }}</span>
          </div>
          <div class="qbody lecture-body" v-html="render(q.body)" />

          <fieldset v-if="q.type === 'mcq_single'" class="options">
            <label v-for="opt in q.options" :key="opt.id" class="option">
              <input type="radio" :name="`q-${q.id}`" :value="opt.id" v-model="qs[q.id].single" />
              <span v-html="render(opt.text)" />
            </label>
          </fieldset>

          <fieldset v-else-if="q.type === 'mcq_multi'" class="options">
            <p class="hint">Select all that apply.</p>
            <label v-for="opt in q.options" :key="opt.id" class="option">
              <input type="checkbox" :value="opt.id" v-model="qs[q.id].multi" />
              <span v-html="render(opt.text)" />
            </label>
          </fieldset>

          <div v-else-if="q.type === 'symbolic'" class="text-answer">
            <label :for="`sym-${q.id}`">Your answer</label>
            <input :id="`sym-${q.id}`" type="text" v-model="qs[q.id].symbolic" />
          </div>

          <div v-else-if="q.type === 'multi_part'" class="parts">
            <div v-for="p in q.parts" :key="p.id" class="part">
              <div class="qbody lecture-body" v-html="render(p.body || '')" />
              <fieldset v-if="p.type === 'mcq_single'" class="options">
                <label v-for="opt in p.options" :key="opt.id" class="option">
                  <input
                    type="radio"
                    :name="`q-${q.id}-${p.id}`"
                    :value="opt.id"
                    v-model="qs[q.id].parts[p.id].single"
                  />
                  <span v-html="render(opt.text)" />
                </label>
              </fieldset>
              <fieldset v-else-if="p.type === 'mcq_multi'" class="options">
                <label v-for="opt in p.options" :key="opt.id" class="option">
                  <input
                    type="checkbox"
                    :value="opt.id"
                    v-model="qs[q.id].parts[p.id].multi"
                  />
                  <span v-html="render(opt.text)" />
                </label>
              </fieldset>
              <div v-else-if="p.type === 'symbolic'" class="text-answer">
                <label>Your answer</label>
                <input type="text" v-model="qs[q.id].parts[p.id].symbolic" />
              </div>
              <div v-else class="text-answer">
                <label>Your answer</label>
                <input type="number" inputmode="decimal" step="any" v-model="qs[q.id].parts[p.id].numeric" />
              </div>
            </div>
          </div>

          <div v-else class="text-answer">
            <label :for="`num-${q.id}`">Your answer</label>
            <input
              :id="`num-${q.id}`"
              type="number"
              inputmode="decimal"
              step="any"
              v-model="qs[q.id].numeric"
            />
          </div>

          <div class="actions">
            <button class="btn" :disabled="qs[q.id].submitting" @click="recordAnswer(q)">
              {{ qs[q.id].submitting ? 'Saving…' : qs[q.id].recorded ? 'Update answer' : 'Record answer' }}
            </button>
            <span v-if="qs[q.id].recorded" class="recorded">
              Recorded<span v-if="qs[q.id].recordedLate"> (after time)</span>
            </span>
          </div>
          <p v-if="qs[q.id].err" class="form-error">{{ qs[q.id].err }}</p>
        </li>
      </ol>

      <div class="submit-bar">
        <button class="btn btn-submit" :disabled="submitting" @click="submitQuiz">
          {{ submitting ? 'Submitting…' : 'Submit quiz' }}
        </button>
      </div>
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
  margin: 0.2rem 0 0.75rem;
}
.quiz-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  position: sticky;
  top: 0;
  background: var(--color-bg);
  padding: 0.4rem 0;
  z-index: 2;
}
.countdown {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  font-size: 1.4rem;
  color: var(--color-text);
  background: var(--color-accent);
  padding: 0.3rem 0.75rem;
  border-radius: 8px;
}
.countdown.low {
  background: var(--color-primary);
  color: var(--color-bg);
}
.lead {
  font-size: 0.9rem;
  margin: 0 0 1rem;
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
.qcard.correct {
  border-color: var(--color-primary);
}
.qcard.incorrect {
  border-color: var(--color-text);
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
.verdict-tag {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  background: var(--color-accent);
  color: var(--color-text);
}
.verdict-tag[data-v='correct'] {
  background: var(--color-primary);
  color: var(--color-bg);
}
.verdict-tag[data-v='incorrect'] {
  background: var(--color-text);
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
.hint {
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
.text-answer {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.text-answer label {
  font-weight: 600;
  font-size: 0.9rem;
}
.text-answer input {
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--color-accent);
  border-radius: 6px;
  font: inherit;
  max-width: 16rem;
}
.parts {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.part {
  padding-left: 0.75rem;
  border-left: 3px solid var(--color-accent);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
  margin-top: 0.9rem;
}
.recorded {
  font-size: 0.85rem;
  color: var(--color-primary);
  font-weight: 600;
}
.your-answer {
  margin: 0.5rem 0;
  font-size: 0.92rem;
}
.late {
  color: var(--color-text);
  font-weight: 700;
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
.scoreline {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  margin-bottom: 1.25rem;
}
.score {
  font-size: 2rem;
  font-weight: 800;
  color: var(--color-primary);
}
.score-detail {
  color: var(--color-text);
  font-size: 0.95rem;
}
.submit-bar {
  margin: 1.5rem 0;
}
.btn-submit {
  width: 100%;
  padding: 0.85rem;
  font-size: 1rem;
}

@media (max-width: 480px) {
  h1 {
    font-size: 1.25rem;
  }
  .qcard {
    padding: 0.85rem 0.9rem;
  }
  .actions {
    flex-direction: column;
    align-items: stretch;
  }
  .actions .btn {
    width: 100%;
  }
  .text-answer input {
    max-width: none;
  }
}
</style>
