import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    // Local dev: proxy /api to the FastAPI server so the frontend can call
    // same-origin relative paths, matching how nginx proxies in production.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      // Uploaded media (animation videos, lecture images). nginx serves this
      // off disk in prod; in dev the API's /media static mount does. No
      // rewrite — the backend serves it at the same /media path.
      '/media': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
