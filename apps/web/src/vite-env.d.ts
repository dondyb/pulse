/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL for API calls from the browser, e.g. "/api" or "http://localhost:8000/api". */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
