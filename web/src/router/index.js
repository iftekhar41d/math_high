import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'

const routes = [
  { path: '/', name: 'home', component: HomeView },
  {
    path: '/about',
    name: 'about',
    // Lazy-loaded so route-based code splitting is wired from the start.
    component: () => import('../views/AboutView.vue'),
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
