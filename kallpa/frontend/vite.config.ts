import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo, /api y /webhook se redirigen al backend FastAPI (puerto 8000).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/webhook': 'http://127.0.0.1:8000',
    },
  },
  build: { outDir: 'dist', sourcemap: false },
})
