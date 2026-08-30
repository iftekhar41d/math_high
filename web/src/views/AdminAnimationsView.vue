<script setup>
// ContentAdmin screen: upload a rendered animation + transcript, fill in the
// metadata, attach it to one or more Topics, preview the draft, and publish it.
// The API refuses every non-ContentAdmin caller with 403, shown here as a plain
// notice. Usable at phone/tablet widths — one column, inputs full-width.
import { computed, onMounted, reactive, ref } from 'vue'
import * as api from '../api'

const loading = ref(true)
const forbidden = ref(false)
const error = ref('')
const status = ref('')
const saving = ref(false)

const animations = ref([])
const topics = ref([])
const selectedSlug = ref(null) // null => the "new animation" form

const form = reactive({
  slug: '',
  title: '',
  description: '',
  duration_seconds: '',
})
const videoFile = ref(null)
const transcriptFile = ref(null)
const attachedTopicIds = ref([])

const selected = computed(() =>
  animations.value.find((a) => a.slug === selectedSlug.value) ?? null,
)
const isNew = computed(() => selected.value === null)

// Topics grouped by Year › Subject › Unit for a legible picker.
const topicGroups = computed(() => {
  const groups = new Map()
  for (const t of topics.value) {
    const key = `${t.year_level_name} › ${t.subject_title} › ${t.unit_title}`
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(t)
  }
  return [...groups.entries()].map(([label, items]) => ({ label, items }))
})

async function loadAll() {
  loading.value = true
  try {
    const [anims, tops] = await Promise.all([
      api.getAdminAnimations(),
      api.getAdminTopics(),
    ])
    animations.value = anims
    topics.value = tops
  } catch (e) {
    if (e.status === 403) forbidden.value = true
    else error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)

function startNew() {
  selectedSlug.value = null
  form.slug = ''
  form.title = ''
  form.description = ''
  form.duration_seconds = ''
  videoFile.value = null
  transcriptFile.value = null
  attachedTopicIds.value = []
  status.value = ''
  error.value = ''
}

function edit(anim) {
  selectedSlug.value = anim.slug
  form.slug = anim.slug
  form.title = anim.title
  form.description = anim.description
  form.duration_seconds = anim.duration_seconds ?? ''
  videoFile.value = null
  transcriptFile.value = null
  attachedTopicIds.value = anim.topics.map((t) => t.id)
  status.value = ''
  error.value = ''
}

function onVideo(e) {
  videoFile.value = e.target.files[0] ?? null
}
function onTranscript(e) {
  transcriptFile.value = e.target.files[0] ?? null
}

async function save() {
  saving.value = true
  status.value = ''
  error.value = ''
  try {
    const saved = await api.saveAdminAnimation({
      slug: form.slug.trim(),
      title: form.title.trim(),
      description: form.description.trim(),
      duration_seconds: form.duration_seconds === '' ? '' : Number(form.duration_seconds),
      video: videoFile.value,
      transcript: transcriptFile.value,
    })
    await api.setAdminAnimationTopics(saved.slug, attachedTopicIds.value)
    await loadAll()
    selectedSlug.value = saved.slug
    edit(animations.value.find((a) => a.slug === saved.slug))
    status.value = 'Saved.'
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

async function publish() {
  status.value = ''
  error.value = ''
  try {
    await api.publishAdminAnimation(selected.value.slug)
    await loadAll()
    status.value = 'Published.'
  } catch (e) {
    // 409 when there is no transcript yet — the API's message says so.
    error.value = e.message
  }
}

async function unpublish() {
  status.value = ''
  error.value = ''
  try {
    await api.unpublishAdminAnimation(selected.value.slug)
    await loadAll()
    status.value = 'Moved back to draft.'
  } catch (e) {
    error.value = e.message
  }
}
</script>

<template>
  <section class="admin">
    <h1>Animations</h1>

    <p v-if="loading">Loading…</p>
    <p v-else-if="forbidden" class="form-error">
      This page is for Content Admins only.
    </p>

    <div v-else class="layout">
      <aside class="list">
        <button type="button" class="btn new-btn" @click="startNew">
          + New animation
        </button>
        <ul>
          <li
            v-for="a in animations"
            :key="a.id"
            :class="{ active: a.slug === selectedSlug }"
          >
            <button type="button" class="link-button" @click="edit(a)">
              <span class="row-title">{{ a.title }}</span>
              <span class="badge" :class="a.status">{{ a.status }}</span>
              <span class="row-slug">{{ a.slug }}</span>
              <span class="row-topics">
                {{ a.topics.length }} topic{{ a.topics.length === 1 ? '' : 's' }}
              </span>
            </button>
          </li>
          <li v-if="!animations.length" class="empty">No animations yet.</li>
        </ul>
      </aside>

      <div class="editor">
        <h2>{{ isNew ? 'New animation' : `Editing “${selected.title}”` }}</h2>

        <form @submit.prevent="save">
          <div class="form-field">
            <label for="slug">Slug</label>
            <input
              id="slug"
              v-model="form.slug"
              type="text"
              required
              :disabled="!isNew"
              placeholder="number-line"
            />
            <p class="hint">The stable key. Re-uploading the same slug updates it.</p>
          </div>

          <div class="form-field">
            <label for="title">Title</label>
            <input id="title" v-model="form.title" type="text" required />
          </div>

          <div class="form-field">
            <label for="description">Description</label>
            <textarea id="description" v-model="form.description" rows="3" />
          </div>

          <div class="form-field">
            <label for="duration">Duration (seconds)</label>
            <input id="duration" v-model="form.duration_seconds" type="number" min="0" />
          </div>

          <div class="form-field">
            <label for="video">
              Video {{ isNew ? '(required)' : '(leave blank to keep current)' }}
            </label>
            <input id="video" type="file" accept="video/*" @change="onVideo" />
          </div>

          <div class="form-field">
            <label for="transcript">
              Transcript (VTT) — required before publishing
            </label>
            <input id="transcript" type="file" accept=".vtt,text/vtt" @change="onTranscript" />
          </div>

          <fieldset class="form-field topics">
            <legend>Attached topics</legend>
            <div v-for="g in topicGroups" :key="g.label" class="topic-group">
              <p class="topic-group-label">{{ g.label }}</p>
              <label v-for="t in g.items" :key="t.id" class="topic-option">
                <input type="checkbox" :value="t.id" v-model="attachedTopicIds" />
                {{ t.title }}
              </label>
            </div>
            <p v-if="!topics.length" class="hint">No topics in the course yet.</p>
          </fieldset>

          <button class="btn" :disabled="saving" type="submit">
            {{ saving ? 'Saving…' : 'Save' }}
          </button>
        </form>

        <template v-if="!isNew">
          <section class="preview">
            <h3>
              Preview
              <span class="badge" :class="selected.status">{{ selected.status }}</span>
            </h3>
            <video class="player" controls preload="metadata" :src="selected.video_url">
              <track
                v-if="selected.transcript_url"
                kind="captions"
                srclang="en"
                label="English"
                :src="selected.transcript_url"
                default
              />
            </video>
            <p v-if="selected.transcript_url" class="transcript-link">
              <a :href="selected.transcript_url" target="_blank" rel="noopener">
                Open transcript
              </a>
            </p>
            <p v-else class="hint">No transcript uploaded yet.</p>

            <div class="publish-row">
              <button
                v-if="selected.status !== 'published'"
                type="button"
                class="btn"
                @click="publish"
              >
                Publish
              </button>
              <button
                v-else
                type="button"
                class="btn secondary"
                @click="unpublish"
              >
                Move back to draft
              </button>
            </div>
          </section>
        </template>

        <p v-if="status" class="save-status">{{ status }}</p>
        <p v-if="error" class="form-error">{{ error }}</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.admin h1 {
  color: var(--color-primary);
  font-size: 1.5rem;
  margin: 0.2rem 0 1rem;
}
.layout {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
  align-items: flex-start;
}
.list {
  flex: 1 1 14rem;
  min-width: 0;
}
.editor {
  flex: 2 1 20rem;
  min-width: 0;
}
.new-btn {
  margin-bottom: 0.75rem;
}
.list ul {
  list-style: none;
  margin: 0;
  padding: 0;
}
.list li {
  border: 1px solid var(--color-accent);
  border-radius: 6px;
  margin-bottom: 0.4rem;
}
.list li.active {
  border-color: var(--color-primary);
}
.list li .link-button {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.15rem 0.5rem;
  width: 100%;
  text-align: left;
  padding: 0.5rem 0.6rem;
  background: none;
  border: none;
  font: inherit;
  color: var(--color-text);
  cursor: pointer;
}
.row-title {
  font-weight: 600;
}
.row-slug,
.row-topics {
  font-size: 0.8rem;
  opacity: 0.7;
}
.row-topics {
  text-align: right;
}
.list li.empty {
  border: none;
  font-size: 0.9rem;
  opacity: 0.7;
}
.badge {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  align-self: start;
}
.badge.draft {
  background: var(--color-accent);
  color: var(--color-text);
}
.badge.published {
  background: var(--color-primary);
  color: var(--color-bg);
}
.editor h2 {
  color: var(--color-primary);
  font-size: 1.15rem;
  margin: 0 0 1rem;
}
.form-field textarea,
.form-field input[type='text'],
.form-field input[type='number'] {
  width: 100%;
  max-width: 30rem;
}
.hint {
  font-size: 0.8rem;
  margin: 0.2rem 0 0;
  opacity: 0.8;
}
.topics {
  border: 1px solid var(--color-accent);
  border-radius: 6px;
  padding: 0.75rem;
}
.topics legend {
  font-weight: 600;
  padding: 0 0.3rem;
}
.topic-group {
  margin-bottom: 0.6rem;
}
.topic-group-label {
  font-size: 0.8rem;
  font-weight: 700;
  opacity: 0.7;
  margin: 0.3rem 0;
}
.topic-option {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.95rem;
  padding: 0.1rem 0;
}
.preview {
  margin-top: 1.5rem;
  border-top: 2px solid var(--color-accent);
  padding-top: 1rem;
}
.preview h3 {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1rem;
  margin: 0 0 0.5rem;
}
.player {
  display: block;
  width: 100%;
  max-width: 640px;
  border-radius: 6px;
  background: var(--color-text);
}
.transcript-link {
  font-size: 0.9rem;
  margin: 0.5rem 0 0;
}
.publish-row {
  margin-top: 1rem;
}
.btn.secondary {
  background: var(--color-accent);
  color: var(--color-text);
}
.save-status {
  color: var(--color-primary);
  font-weight: 600;
}

@media (max-width: 640px) {
  .layout {
    flex-direction: column;
  }
  .list,
  .editor {
    flex: 1 1 auto;
    width: 100%;
  }
  .form-field textarea,
  .form-field input[type='text'],
  .form-field input[type='number'] {
    max-width: 100%;
  }
  .player {
    max-width: 100%;
  }
}
</style>
