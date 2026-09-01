import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Deliberately no `server.proxy` here, even though proxying /api to Django is
// the usual Vite trick. Django's dev settings are already set up for a real
// cross-origin request from localhost:5173 -- CORS_ALLOW_CREDENTIALS, the
// Lax cookie flags, CSRF_TRUSTED_ORIGINS -- because production genuinely is
// cross-origin (different hosts, SameSite=None).
//
// A proxy would make dev same-origin and hide every cookie and CSRF mistake
// until deploy day, which is the worst possible time to find them. Slightly
// more friction now, no nasty surprise later.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Fail loudly rather than silently sliding to 5174 if the port is taken.
    // Django's CORS allowlist names 5173 exactly, so a "helpful" fallback
    // would produce a confusing wall of CORS errors instead.
    strictPort: true,
  },
})
