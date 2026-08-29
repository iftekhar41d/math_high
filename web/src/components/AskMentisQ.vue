<script setup>
// "Ask MentisQ" — a multi-turn guided conversation with the AI tutor. Drops onto
// a lecture page (pass `topicSlug`), a practice question (pass `questionId`), or
// a standalone page (pass neither). The student keeps replying in the thread and
// MentisQ sees the recent history; the tutor's replies render maths (KaTeX) via
// the shared lecture renderer. Launching from a different Topic/Question opens a
// fresh conversation; the standalone page resumes the most recent general chat.
import { computed, onMounted, ref } from 'vue'
import * as api from '../api'
import { renderLecture } from '../lib/lecture'

const props = defineProps({
  topicSlug: { type: String, default: null },
  questionId: { type: Number, default: null },
  // Start expanded on a dedicated page; collapsed when embedded.
  startOpen: { type: Boolean, default: false },
})

const isGeneral = computed(
  () => !props.topicSlug && props.questionId == null,
)

const open = ref(props.startOpen)
const draft = ref('')
const sending = ref(false)
const error = ref('')
// { role: 'user' | 'assistant', content, status }  (status only on assistant)
const turns = ref([])
const sessionId = ref(null)
const helpful = ref(null)
// Set by "New chat" so the next send starts a fresh conversation server-side.
const startFresh = ref(false)

const context = computed(() => {
  if (props.topicSlug) return { topic_slug: props.topicSlug }
  if (props.questionId != null) return { question_id: props.questionId }
  return {}
})

const canRate = computed(
  () =>
    sessionId.value != null &&
    turns.value.some((t) => t.role === 'assistant' && t.status === 'ok'),
)

function renderTurn(turn) {
  return turn.role === 'assistant' && turn.status === 'ok'
    ? renderLecture(turn.content)
    : ''
}

onMounted(async () => {
  if (!isGeneral.value) return
  try {
    const s = await api.getCurrentMentisQSession()
    if (s && s.turns.length) {
      sessionId.value = s.session_id
      helpful.value = s.helpful
      turns.value = s.turns.map((t) => ({ ...t, status: 'ok' }))
    }
  } catch {
    // A missing prior session is not an error worth showing.
  }
})

async function send() {
  const content = draft.value.trim()
  if (!content || sending.value) return
  sending.value = true
  error.value = ''
  turns.value.push({ role: 'user', content })
  draft.value = ''
  try {
    const opts = {}
    if (sessionId.value != null && !startFresh.value)
      opts.session_id = sessionId.value
    if (startFresh.value) opts.new_chat = true

    const res = await api.askMentisQ(content, context.value, opts)
    turns.value.push({
      role: 'assistant',
      content: res.reply,
      status: res.status,
    })
    if (res.status !== 'limit_reached') {
      if (res.session_id !== sessionId.value) helpful.value = null
      sessionId.value = res.session_id
      startFresh.value = false
    }
  } catch (e) {
    error.value = e.message
    turns.value.pop() // drop the unsent user turn so it can be retried
    draft.value = content
  } finally {
    sending.value = false
  }
}

function newChat() {
  turns.value = []
  sessionId.value = null
  helpful.value = null
  error.value = ''
  startFresh.value = true
}

async function rate(value) {
  if (sessionId.value == null) return
  const next = helpful.value === value ? null : value
  helpful.value = next
  try {
    await api.rateMentisQSession(sessionId.value, next)
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <section class="ask">
    <button
      v-if="!open"
      type="button"
      class="btn btn-secondary ask-toggle"
      @click="open = true"
    >
      Ask MentisQ
    </button>

    <div v-else class="ask-panel">
      <div class="ask-head">
        <h3>Ask MentisQ</h3>
        <div class="ask-head-actions">
          <button
            v-if="turns.length"
            type="button"
            class="link-button"
            @click="newChat"
          >
            New chat
          </button>
          <button
            v-if="!startOpen"
            type="button"
            class="link-button"
            @click="open = false"
          >
            Close
          </button>
        </div>
      </div>
      <p class="ask-note">
        MentisQ guides you toward the answer — it won’t just hand it over. Keep
        replying to work through it step by step.
      </p>

      <div v-if="turns.length" class="ask-thread">
        <div
          v-for="(turn, i) in turns"
          :key="i"
          class="msg"
          :class="`msg-${turn.role}`"
          :data-status="turn.status"
        >
          <div
            v-if="turn.role === 'assistant' && turn.status === 'ok'"
            class="lecture-body msg-body"
            v-html="renderTurn(turn)"
          />
          <p v-else class="msg-body">{{ turn.content }}</p>
        </div>
      </div>

      <div v-if="canRate" class="ask-rate">
        <span>Did this help?</span>
        <button
          type="button"
          class="rate-btn"
          :class="{ active: helpful === true }"
          aria-label="This helped"
          @click="rate(true)"
        >
          👍
        </button>
        <button
          type="button"
          class="rate-btn"
          :class="{ active: helpful === false }"
          aria-label="This didn’t help"
          @click="rate(false)"
        >
          👎
        </button>
      </div>

      <textarea
        v-model="draft"
        rows="3"
        :placeholder="
          turns.length
            ? 'Reply to MentisQ… (Ctrl+Enter to send)'
            : 'What are you stuck on? Show your working for a more useful hint.'
        "
        @keydown.ctrl.enter="send"
      />
      <div class="ask-actions">
        <button class="btn" :disabled="!draft.trim() || sending" @click="send">
          {{ sending ? 'Thinking…' : turns.length ? 'Send' : 'Ask' }}
        </button>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>
    </div>
  </section>
</template>

<style scoped>
.ask {
  margin-top: 1.5rem;
}
.ask-panel {
  border: 1px solid var(--color-accent);
  border-radius: 10px;
  padding: 1rem 1.1rem;
  background: var(--color-bg);
}
.ask-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
}
.ask-head-actions {
  display: flex;
  gap: 0.9rem;
  flex-shrink: 0;
}
.ask-head h3 {
  margin: 0;
  color: var(--color-primary);
  font-size: 1rem;
}
.ask-note {
  font-size: 0.85rem;
  margin: 0.3rem 0 0.6rem;
}
.ask-thread {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  margin: 0.8rem 0;
  max-height: 55vh;
  overflow-y: auto;
}
.msg {
  max-width: 90%;
  padding: 0.6rem 0.8rem;
  border-radius: 10px;
  font-size: 0.92rem;
}
.msg-body {
  margin: 0;
}
.msg-user {
  align-self: flex-end;
  background: var(--color-primary);
  color: var(--color-bg);
  border-bottom-right-radius: 3px;
}
.msg-assistant {
  align-self: flex-start;
  background: var(--color-accent);
  color: var(--color-dark);
  border-bottom-left-radius: 3px;
}
.msg-assistant[data-status='failed'],
.msg-assistant[data-status='limit_reached'] {
  background: var(--color-bg);
  border: 1px dashed var(--color-primary);
  font-size: 0.88rem;
}
.ask-rate {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  margin-bottom: 0.7rem;
}
.rate-btn {
  border: 1px solid var(--color-accent);
  background: var(--color-bg);
  border-radius: 6px;
  padding: 0.15rem 0.45rem;
  font-size: 0.95rem;
  cursor: pointer;
  line-height: 1;
}
.rate-btn.active {
  border-color: var(--color-primary);
  background: var(--color-accent);
}
textarea {
  width: 100%;
  border: 1px solid var(--color-accent);
  border-radius: 6px;
  padding: 0.5rem 0.6rem;
  font: inherit;
  resize: vertical;
}
.ask-actions {
  margin-top: 0.6rem;
}
.link-button {
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  color: var(--color-primary);
  cursor: pointer;
}
@media (max-width: 480px) {
  .ask-panel {
    padding: 0.85rem 0.8rem;
  }
  .msg {
    max-width: 100%;
  }
}
</style>
