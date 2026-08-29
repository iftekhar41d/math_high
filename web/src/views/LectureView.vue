<script setup>
// The lecture reader: a Topic's LectureContent rendered with maths (KaTeX),
// callouts, worked examples and images, plus its prerequisite Topics as links.
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import * as api from '../api'
import { renderLecture } from '../lib/lecture'

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
</script>

<template>
  <article class="lecture">
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

      <RouterLink
        class="btn practice-cta"
        :to="{ name: 'learn-practice', params: { slug: topic.slug } }"
      >
        Practise this topic →
      </RouterLink>
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
</style>
