import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/', name: 'home', component: HomeView },
  {
    path: '/about',
    name: 'about',
    // Lazy-loaded so route-based code splitting is wired from the start.
    component: () => import('../views/AboutView.vue'),
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('../views/RegisterView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/verify-email',
    name: 'verify-email',
    component: () => import('../views/VerifyEmailView.vue'),
  },
  {
    path: '/forgot-password',
    name: 'forgot-password',
    component: () => import('../views/ForgotPasswordView.vue'),
    meta: { guestOnly: true },
  },
  {
    path: '/reset-password',
    name: 'reset-password',
    component: () => import('../views/ResetPasswordView.vue'),
  },
  {
    path: '/profile',
    name: 'profile',
    component: () => import('../views/ProfileView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('../views/DashboardView.vue'),
    meta: { requiresAuth: true },
  },
  // Course browsing: Year Level → Subject → Unit → Topic. One component drives
  // every list level (it keys off the route name); the lecture reader is its
  // own view.
  {
    path: '/learn',
    name: 'learn',
    component: () => import('../views/BrowseView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/learn/years/:yearLevelId',
    name: 'learn-year',
    component: () => import('../views/BrowseView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/learn/subjects/:subjectId',
    name: 'learn-subject',
    component: () => import('../views/BrowseView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/learn/units/:unitId',
    name: 'learn-unit',
    component: () => import('../views/BrowseView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/learn/topics/:slug',
    name: 'learn-topic',
    component: () => import('../views/LectureView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/learn/topics/:slug/practice',
    name: 'learn-practice',
    component: () => import('../views/PracticeView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/mentisq',
    name: 'mentisq',
    component: () => import('../views/MentisQView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/admin/mentisq',
    name: 'admin-mentisq',
    component: () => import('../views/AdminMentisQView.vue'),
    meta: { requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// The auth store restores the session once (`restore()` in main.js); the guard
// just waits for that to settle before deciding.
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.ready) {
    await auth.restore()
  }
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.guestOnly && auth.isAuthenticated) {
    return { name: 'profile' }
  }
  return true
})

export default router
