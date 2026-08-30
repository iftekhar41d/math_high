<script setup>
// The lecture reader: a Topic's LectureContent rendered with maths (KaTeX),
// callouts, worked examples and images, plus its prerequisite Topics as links.
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import * as api from '../api'
import { renderLecture } from '../lib/lecture'
import AskMentisQ from '../components/AskMentisQ.vue'

const route = useRoute()

const topic = ref(null)
const error = ref('')
const loading = ref(false)
const notFound = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  notFound.value = false
  topic.value = null
  try {
    topic.value = await api.getTopic(route.params.slug)
  } catch (e) {
    if (e.status === 404) notFound.value = true
    else error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(() => route.params.slug, load, { immediate: true })

const bodyHtml = computed(() =>
  topic.value?.lecture_content
    ? renderLecture(topic.value.lecture_content.body)
    : '',
)
const isDraft = computed(
  () => topic.value?.lecture_content?.status === 'draft',
)
const animations = computed(() => topic.value?.animations ?? [])

function runtime(seconds) {
  if (!seconds) return ''
  const m = Math.floor(seconds / 60)
  const s = String(seconds % 60).padStart(2, '0')
  return `${m}:${s}`
}
</script>

<template>
  <article class="lecture">
    <nav class="crumbs">
      <button type="button" class="link-button" @click="$router.back()">← Back</button>
      <RouterLink :to="{ name: 'learn' }">Course</RouterLink>
    </nav>

    <p v-if="loading">Loading…</p>
    <p v-else-if="error" class="form-error">{{ error }}</p>
    <p v-else-if="notFound" class="form-error">
      That topic isn’t available.
      <RouterLink :to="{ name: 'learn' }">Browse the course</RouterLink>.
    </p>

    <template v-else-if="topic">
      <header>
        <span v-if="isDraft" class="draft-badge">Draft</span>
        <h1>{{ topic.title }}</h1>
      </header>

      <section v-if="topic.prerequisites.length" class="prereqs">
        <h2>Before this, revise</h2>
        <ul>
          <li v-for="p in topic.prerequisites" :key="p.id">
            <RouterLink :to="{ name: 'learn-topic', params: { slug: p.slug } }">
              {{ p.title }}
            </RouterLink>
          </li>
        </ul>
      </section>

      <div v-if="bodyHtml" class="lecture-body" v-html="bodyHtml" />
      <p v-else>This topic has no lecture content yet.</p>

      <section v-if="animations.length" class="animations">
        <h2>Animations</h2>
        <article v-for="a in animations" :key="a.id" class="animation">
          <h3>
            {{ a.title }}
            <span v-if="runtime(a.duration_seconds)" class="animation-runtime">
              {{ runtime(a.duration_seconds) }}
            </span>
            <span v-if="a.status === 'draft'" class="draft-badge">Draft</span>
          </h3>
          <p v-if="a.description" class="animation-desc">{{ a.description }}</p>
          <video
            class="animation-player"
            controls
            preload="metadata"
            :src="a.video_url"
          >
            <track
              v-if="a.transcript_url"
              kind="captions"
              srclang="en"
              label="English"
              :src="a.transcript_url"
              default
            />
          </video>
          <p v-if="a.transcript_url" class="animation-transcript">
            <a :href="a.transcript_url" target="_blank" rel="noopener">
              Open transcript
            </a>
          </p>
        </article>
      </section>

      <RouterLink
        class="btn practice-cta"
        :to="{ name: 'learn-practice', params: { slug: topic.slug } }"
      >
        Practise this topic →
      </RouterLink>

      <AskMentisQ :topic-slug="topic.slug" />
    </template>
  </article>
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
header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}
h1 {
  color: var(--color-primary);
  font-size: 1.6rem;
  margin: 0.2rem 0 1rem;
}
.draft-badge {
  background: var(--color-primary);
  color: var(--color-bg);
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
}
.prereqs {
  background: var(--color-accent);
  border-radius: 8px;
  padding: 0.75rem 1rem;
  margin-bottom: 1.5rem;
}
.prereqs h2 {
  font-size: 0.95rem;
  margin: 0 0 0.4rem;
}
.prereqs ul {
  margin: 0;
  padding-left: 1.1rem;
}
.practice-cta {
  display: inline-block;
  margin-top: 2rem;
  text-decoration: none;
}
.animations {
  margin-top: 2rem;
}
.animations > h2 {
  color: var(--color-primary);
  font-size: 1.2rem;
  margin: 0 0 0.75rem;
}
.animation {
  background: var(--color-accent);
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
}
.animation h3 {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  font-size: 1rem;
  margin: 0 0 0.4rem;
}
.animation-runtime {
  font-size: 0.8rem;
  font-weight: 400;
  color: var(--color-primary);
  font-variant-numeric: tabular-nums;
}
.animation-desc {
  margin: 0 0 0.75rem;
  font-size: 0.95rem;
}
.animation-player {
  display: block;
  width: 100%;
  max-width: 640px;
  height: auto;
  border-radius: 6px;
  background: var(--color-text);
}
.animation-transcript {
  margin: 0.5rem 0 0;
  font-size: 0.9rem;
}
</style>
