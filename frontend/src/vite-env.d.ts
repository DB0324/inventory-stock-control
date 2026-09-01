/// <reference types="vite/client" />

// Typing the env vars we actually read, so a typo in import.meta.env is a
// compile error instead of an undefined at runtime.
interface ImportMetaEnv {
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
