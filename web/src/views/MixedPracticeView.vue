<script setup>
// Mixed practice over a Unit: a set of questions sampled across the Unit's
// Topics at session start, weighted toward the SkillTags where the student is
// weakest (an even spread when there's no mastery data yet). Worked one
// question at a time with immediate feedback and worked solutions — exactly
// like Topic practice; nothing is withheld. Each visit starts a fresh run.
import { reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import * as api from '../api'
import { renderLecture } from '../lib/lecture'
import AskMentisQ from '../components/AskMentisQ.vue'

const route = useRoute()

const session = ref(null) // MixedSessionOut
const loading = ref(false)
const error = ref('')

// Per-question interaction state, keyed by question id.
const qs = reactive({})

function freshState(q) {
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
    result: null, // { is_correct, attempt_no, worked_solution }
    solution: '',
    err: '',
  }
}

function resetState(questions) {
  for (const k of Object.keys(qs)) delete qs[k]
  for (const q of questions) qs[q.id] = freshState(q)
}

async function load() {
  loading.value = true
  error.value = ''
  session.value = null
  try {
    const data = await api.startMixedPractice('unit', route.params.unitId)
    session.value = data
    resetState(data.questions)
  } catch (e) {
    error.value = e.message || 'Could not start mixed practice.'
  } finally {
    loading.value = false
  }
}

// Watch the full path (not just the param) so "New mixed set" — which re-navigates
// here with a fresh `?t=` — actually rebuilds the run.
watch(() => route.fullPath, load, { immediate: true })

const render = (text) => renderLecture(text)

// One answer shape per question type, off the per-question (or per-part) state.
function readAnswer(type, st) {
  if (type === 'mcq_single') return st.single
  if (type === 'mcq_multi') return [...st.multi]
  if (type === 'symbolic') return st.symbolic
  return st.numeric === '' ? null : Number(st.numeric)
}

function buildAnswer(q, s) {
  if (q.type === 'multi_part') {
    const out = {}
    for (const p of q.parts || []) out[p.id] = readAnswer(p.type, s.parts[p.id])
    return out
  }
  return readAnswer(q.type, s)
}

function canSubmit(q) {
  const s = qs[q.id]
  if (s.submitting) return false
  if (q.type === 'mcq_single') return s.single !== ''
  if (q.type === 'mcq_multi') return s.multi.length > 0
  if (q.type === 'symbolic') return s.symbolic.trim() !== ''
  if (q.type === 'multi_part') return true
  return s.numeric !== '' && !Number.isNaN(Number(s.numeric))
}

async function submit(q) {
  const s = qs[q.id]
  s.err = ''
  s.submitting = true
  const elapsed = Math.max(1, Math.round((Date.now() - s.startedAt) / 1000))
  try {
    const res = await api.submitAnswer(q.id, buildAnswer(q, s), elapsed)
    s.result = res
    s.solution = res.worked_solution || s.solution
  } catch (e) {
    s.err = e.message || 'Could not check that answer.'
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
    s.err = e.message || 'Could not load the solution.'
  }
}
</script>

<template>
  <section class="mixed">
    <nav class="crumbs">
      <button type="button" class="link-button" @click="$router.back()">← Back</button>
      <RouterLink :to="{ name: 'learn' }">Course</RouterLink>
    </nav>

    <p v-if="loading">Building your mixed set…</p>
    <p v-else-if="error" class="form-error">{{ error }}</p>

    <template v-else-if="session">
      <h1>Mixed practice: {{ session.scope_label }}</h1>
      <p class="lead">
        Questions from across this unit, leaning toward the skills you need most.
        Immediate feedback, just like topic practice.
      </p>
      <p v-if="session.questions.length === 0">
        There are no practice questions in this unit yet.
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
            <input
              :id="`sym-${q.id}`"
              type="text"
              v-model="qs[q.id].symbolic"
              @keyup.enter="canSubmit(q) && submit(q)"
            />
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
                <input
                  type="number"
                  inputmode="decimal"
                  step="any"
                  v-model="qs[q.id].parts[p.id].numeric"
                />
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

      <RouterLink
        class="btn btn-secondary retake"
        :to="{ name: 'learn-mixed-practice', params: route.params, query: { t: Date.now() } }"
      >
        New mixed set
      </RouterLink>
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
  margin: 0.2rem 0 0.5rem;
}
.lead {
  font-size: 0.9rem;
  margin: 0 0 1.25rem;
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
.retake {
  display: inline-block;
  margin-top: 1.5rem;
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
  }
  .actions .btn {
    width: 100%;
  }
  .text-answer input {
    max-width: none;
  }
}
</style>
