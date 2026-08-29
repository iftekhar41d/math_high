<script setup>
// "Ask MentisQ" — a single guided exchange with the AI tutor. Drops onto a
// lecture page (pass `topicSlug`), a practice question (pass `questionId`), or
// a standalone page (pass neither). The tutor's reply is rendered with maths
// (KaTeX) via the shared lecture renderer.
import { computed, ref } from 'vue'
import * as api from '../api'
import { renderLecture } from '../lib/lecture'

const props = defineProps({
  topicSlug: { type: String, default: null },
  questionId: { type: Number, default: null },
  // Start expanded on a dedicated page; collapsed when embedded.
  startOpen: { type: Boolean, default: false },
})

const open = ref(props.startOpen)
const question = ref('')
const sending = ref(false)
const error = ref('')
const reply = ref(null) // { reply, status }

const context = computed(() => {
  if (props.topicSlug) return { topic_slug: props.topicSlug }
  if (props.questionId != null) return { question_id: props.questionId }
  return {}
})

const replyHtml = computed(() =>
  reply.value ? renderLecture(reply.value.reply) : '',
)

async function send() {
  if (!question.value.trim() || sending.value) return
  sending.value = true
  error.value = ''
  reply.value = null
  try {
    reply.value = await api.askMentisQ(question.value.trim(), context.value)
  } catch (e) {
    error.value = e.message
  } finally {
    sending.value = false
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
        <button
          v-if="!startOpen"
          type="button"
          class="link-button"
          @click="open = false"
        >
          Close
        </button>
      </div>
      <p class="ask-note">
        MentisQ guides you toward the answer — it won’t just hand it over.
      </p>

      <textarea
        v-model="question"
        rows="3"
        placeholder="What are you stuck on? Show your working for a more useful hint."
        @keydown.ctrl.enter="send"
      />
      <div class="ask-actions">
        <button class="btn" :disabled="!question.trim() || sending" @click="send">
          {{ sending ? 'Thinking…' : 'Ask' }}
        </button>
      </div>

      <p v-if="error" class="form-error">{{ error }}</p>

      <div v-if="reply" class="ask-reply" :data-status="reply.status">
        <p v-if="reply.status === 'limit_reached'" class="ask-status">
          {{ reply.reply }}
        </p>
        <p v-else-if="reply.status === 'failed'" class="ask-status">
          {{ reply.reply }}
        </p>
        <div v-else class="lecture-body" v-html="replyHtml" />
      </div>
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
.ask-head h3 {
  margin: 0;
  color: var(--color-primary);
  font-size: 1rem;
}
.ask-note {
  font-size: 0.85rem;
  margin: 0.3rem 0 0.6rem;
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
.ask-reply {
  margin-top: 0.9rem;
  padding: 0.85rem 1rem;
  background: var(--color-accent);
  border-radius: 8px;
}
.ask-reply[data-status='limit_reached'],
.ask-reply[data-status='failed'] {
  background: var(--color-bg);
  border: 1px dashed var(--color-primary);
}
.ask-status {
  margin: 0;
  font-size: 0.9rem;
}
</style>
