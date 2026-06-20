import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Monorepo dev layout (build-plan.md): Vite dev server proxies API calls to uvicorn.
// For the demo build, FastAPI serves the static bundle from dist/.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 4317,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
