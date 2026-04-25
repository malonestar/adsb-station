import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// When running `npm run dev` on Windows, you typically want to proxy API+WS
// to the Pi. When built and served inside the adsb-frontend container, nginx
// handles that — no proxy needed.
const PI = process.env.VITE_PI_HOST ?? 'http://192.168.0.113:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': { target: PI, changeOrigin: true },
      '/ws': { target: PI.replace('http', 'ws'), ws: true, changeOrigin: true },
    },
  },
  build: {
    target: 'es2022',
    sourcemap: true,
    chunkSizeWarningLimit: 1500,
  },
})
