import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Demo builds are served from a GitHub Pages project subpath
  // (https://hadesxgod1337.github.io/loregraph/); the real app is served from
  // root. VITE_DEMO also flips the frontend onto its in-memory fake backend.
  base: process.env.VITE_DEMO ? "/loregraph/" : "/",
  server: {
    host: "127.0.0.1",
  },
})
