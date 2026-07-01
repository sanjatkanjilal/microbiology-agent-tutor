import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],

  // Dev server: proxy /api and /case-images calls to FastAPI so you don't
  // need a local copy of the image files or hit CORS.
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
      '/case-images': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
    },
  },

  // Production build: output into FastAPI's static/react directory
  build: {
    outDir: '../src/microtutor/api/static/react',
    emptyOutDir: true,
  },
})
