<script setup>
// App shell: a header with nav and the routed view. Screens live in src/views.
import { computed } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useAuthStore } from './stores/auth'
import logoUrl from './assets/mentisq-logo.png'

const auth = useAuthStore()
const router = useRouter()
const { user, isAuthenticated } = storeToRefs(auth)

const isSuperAdmin = computed(() => user.value?.role === 'super_admin')
const isContentAdmin = computed(() => user.value?.role === 'content_admin')

async function signOut() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="app">
    <header class="app-header">
      <div class="app-header-inner">
        <RouterLink to="/" class="brand" aria-label="MentisQ home">
          <img :src="logoUrl" alt="MentisQ" class="brand-logo" />
        </RouterLink>
        <nav>
          <RouterLink to="/" class="nav-home" aria-label="Home">
            <svg class="nav-home-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path
                d="M3 11.5 12 4l9 7.5M5.5 10v9a1 1 0 0 0 1 1H10v-5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v5h3.5a1 1 0 0 0 1-1v-9"
              />
            </svg>
          </RouterLink>
          <RouterLink v-if="isAuthenticated" to="/dashboard">Dashboard</RouterLink>
          <RouterLink v-if="isAuthenticated" to="/learn">Learn</RouterLink>
          <RouterLink v-if="isAuthenticated" to="/mentisq">Ask MentisQ</RouterLink>
          <RouterLink v-if="isContentAdmin" to="/admin/animations">Animations</RouterLink>
          <RouterLink v-if="isSuperAdmin" to="/admin/mentisq">Settings</RouterLink>
          <RouterLink to="/about">About</RouterLink>
        </nav>
        <div class="spacer" />
        <nav v-if="isAuthenticated" class="account">
          <RouterLink to="/profile">{{ user.name }}</RouterLink>
          <button
            type="button"
            class="link-button logout-button"
            aria-label="Log out"
            title="Log out"
            @click="signOut"
          >
            <svg class="logout-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 8l-4 4 4 4M6 12h11" />
            </svg>
          </button>
        </nav>
        <nav v-else class="account">
          <RouterLink to="/login">Log in</RouterLink>
          <RouterLink to="/register">Register</RouterLink>
        </nav>
      </div>
    </header>

    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app {
  /* One column width + gutter, shared by the header bar and the page body so
     they stay aligned. Gutter shrinks on narrow screens. */
  --content-max: 1120px;
  --content-gutter: clamp(1rem, 5vw, 2.5rem);
}
.app-header {
  background: var(--color-header);
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 1px 4px rgba(12, 58, 61, 0.18);
}
.app-header-inner {
  max-width: var(--content-max);
  margin: 0 auto;
  padding: 1rem var(--content-gutter);
  display: flex;
  align-items: center;
  gap: 1.5rem;
}
.spacer {
  flex: 1;
}
.brand {
  display: flex;
  align-items: center;
}
.brand-logo {
  display: block;
  height: 32px;
  width: auto;
}
nav {
  display: flex;
  gap: 1rem;
  align-items: center;
}
nav a {
  text-decoration: none;
  color: #fff;
}
nav a:hover {
  color: rgba(255, 255, 255, 0.8);
}
nav a.router-link-active {
  font-weight: 600;
  text-decoration: underline;
}
.nav-home {
  display: flex;
  align-items: center;
}
.nav-home.router-link-active {
  text-decoration: none;
  font-weight: 400;
}
.nav-home-icon {
  width: 22px;
  height: 22px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.nav-home.router-link-exact-active .nav-home-icon {
  stroke-width: 2.6;
}
.link-button {
  background: none;
  border: none;
  padding: 0;
  font: inherit;
  color: #fff;
  cursor: pointer;
}
.logout-button {
  display: flex;
  align-items: center;
}
.logout-button:hover {
  color: rgba(255, 255, 255, 0.8);
}
.logout-icon {
  width: 22px;
  height: 22px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.app-main {
  max-width: var(--content-max);
  margin: 0 auto;
  padding: 1.5rem var(--content-gutter);
}

@media (max-width: 560px) {
  .app-header-inner {
    flex-wrap: wrap;
    gap: 0.5rem 1rem;
  }
  nav {
    gap: 0.75rem 1rem;
    flex-wrap: wrap;
  }
  .spacer {
    flex-basis: 100%;
  }
}
</style>
