import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// No server.proxy, deliberately. Proxying /api to Django would make dev
// same-origin and hide every cookie and CSRF mistake until deploy day --
// production is genuinely cross-origin, and dev.py is already configured for
// that with CORS_ALLOW_CREDENTIALS and CSRF_TRUSTED_ORIGINS.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // strictPort makes the pin real. dev.py's CORS_ALLOWED_ORIGINS names
    // http://localhost:5173 exactly; if the port were taken and Vite
    // helpfully slid to 5174, the session cookie would stop being sent and
    // every request would arrive anonymous with no obvious cause. Better to
    // fail on startup with "port in use" than to debug that.
    strictPort: true,
  },
});
