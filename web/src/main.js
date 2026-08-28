import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import './style.css'

const app = createApp(App)
app.use(createPinia())

// Trade the refresh cookie for an access token before the first route resolves,
// so a reload lands the user back where they were instead of bouncing to /login.
const auth = useAuthStore()
auth.restore().finally(() => {
  app.use(router)
  app.mount('#app')
})
