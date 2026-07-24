/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend base URL for the real app (see api/client.ts). */
  readonly VITE_API_URL?: string;
  /** "1" in the GitHub Pages demo build — routes all API calls to the
   * in-memory fake backend (api/demo/) and switches to a hash router. */
  readonly VITE_DEMO?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
