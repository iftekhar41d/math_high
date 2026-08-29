<script setup>
// Standalone "Ask MentisQ" page — a general maths question with no Topic or
// Question context.
import AskMentisQ from '../components/AskMentisQ.vue'
</script>

<template>
  <section class="mentisq-page">
    <h1>Ask MentisQ</h1>
    <p class="lede">
      Bring any maths question. MentisQ nudges you toward the answer with hints
      and questions rather than solving it for you. Open a lecture or a practice
      question first if you want MentisQ to know exactly what you’re working on.
    </p>
    <AskMentisQ start-open />
  </section>
</template>

<style scoped>
.mentisq-page h1 {
  color: var(--color-primary);
  font-size: 1.5rem;
  margin: 0.2rem 0 0.75rem;
}
.lede {
  margin: 0 0 1rem;
}
</style>
