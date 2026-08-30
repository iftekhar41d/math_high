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
  // Course browsing: a two-pane screen (Subject + Units on the left, the
  // selected Unit's Topics on the right). The selected Unit is carried in the
  // URL; `/learn` bare auto-selects the first Unit. The lecture reader, practice
  // and quiz flows are their own views.
  {
    path: '/learn',
    name: 'learn',
    component: () => import('../views/CourseView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/learn/units/:unitId',
    name: 'learn-unit',
    component: () => import('../views/CourseView.vue'),
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
    path: '/learn/units/:unitId/timed-quiz',
    name: 'learn-timed-quiz',
    component: () => import('../views/TimedQuizView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/learn/units/:unitId/mixed-practice',
    name: 'learn-mixed-practice',
    component: () => import('../views/MixedPracticeView.vue'),
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
  {
    path: '/admin/animations',
    name: 'admin-animations',
    component: () => import('../views/AdminAnimationsView.vue'),
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
    return { name: 'learn' }
  }
  return true
})

export default router
