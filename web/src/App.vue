<script setup>
// App shell: a header with nav and the routed view. Screens live in src/views.
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="app">
    <header class="app-header">
      <span class="brand">MentisQ</span>
      <nav>
        <RouterLink to="/">Home</RouterLink>
        <RouterLink to="/about">About</RouterLink>
      </nav>
    </header>

    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app {
  max-width: 720px;
  margin: 0 auto;
  padding: 0 1rem;
}
.app-header {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 1rem 0;
  border-bottom: 2px solid var(--color-accent);
}
.brand {
  font-weight: 700;
  font-size: 1.25rem;
  color: var(--color-primary);
}
nav {
  display: flex;
  gap: 1rem;
}
nav a {
  text-decoration: none;
}
nav a.router-link-active {
  font-weight: 600;
  text-decoration: underline;
}
.app-main {
  padding: 1.5rem 0;
}
</style>
