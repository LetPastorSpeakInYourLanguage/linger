import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev (`npm run dev`) the API + media streaming live on the FastAPI backend
// (default :8000). Proxy the backend routes through Vite so relative fetches in
// api.js work with hot-reload, exactly as they do when the backend serves the
// built bundle in production.
// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(
      ['/api', '/stream'].map((p) => [p, 'http://localhost:8000'])
    ),
  },
})
