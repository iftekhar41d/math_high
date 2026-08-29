<script setup>
// App shell: a header with nav and the routed view. Screens live in src/views.
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const router = useRouter()
const { user, isAuthenticated } = storeToRefs(auth)

async function signOut() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="app">
    <header class="app-header">
      <span class="brand">MentisQ</span>
      <nav>
        <RouterLink to="/">Home</RouterLink>
        <RouterLink v-if="isAuthenticated" to="/learn">Learn</RouterLink>
        <RouterLink to="/about">About</RouterLink>
      </nav>
      <div class="spacer" />
      <nav v-if="isAuthenticated" class="account">
        <RouterLink to="/profile">{{ user.name }}</RouterLink>
        <button type="button" class="link-button" @click="signOut">Log out</button>
      </nav>
      <nav v-else class="account">
        <RouterLink to="/login">Log in</RouterLink>
        <RouterLink to="/register">Register</RouterLink>
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
.spacer {
  flex: 1;
}
.brand {
  font-weight: 700;
  font-size: 1.25rem;
  color: var(--color-primary);
}
nav {
  display: flex;
  gap: 1rem;
  align-items: center;
}
nav a {
  text-decoration: none;
}
nav a.router-link-active {
  font-weight: 600;
  text-decoration: underline;
}
.link-button {
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  color: var(--color-primary);
  cursor: pointer;
}
.app-main {
  padding: 1.5rem 0;
}
</style>
