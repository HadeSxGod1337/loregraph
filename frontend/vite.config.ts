import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Optional private UI extension package (separate repo, not published here,
// installed manually with `npm install --no-save git+ssh://...` before a
// private build — see backend/pyproject.toml's `private` extra for the
// equivalent on the Python side). When it's not installed, the import
// resolves to a local no-op stub instead of failing the build — Rollup
// needs the module to resolve either way, unlike Python's importlib.metadata
// which tolerates a missing entry point at runtime.
const privateUiEntry = fileURLToPath(
  new URL('./node_modules/@loregraph/private-ui', import.meta.url),
)
const hasPrivateUi = existsSync(privateUiEntry)

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Demo builds are served from a GitHub Pages project subpath
  // (https://hadesxgod1337.github.io/loregraph/); the real app is served from
  // root. VITE_DEMO also flips the frontend onto its in-memory fake backend.
  base: process.env.VITE_DEMO ? "/loregraph/" : "/",
  resolve: {
    alias: hasPrivateUi
      ? {}
      : {
          '@loregraph/private-ui': fileURLToPath(
            new URL('./src/plugins/privateUiStub.ts', import.meta.url),
          ),
        },
  },
  server: {
    host: "127.0.0.1",
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
})
