import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// No server.proxy in dev, deliberately -- and note this now makes development
// STRICTER than production rather than matching it.
//
// Production proxies /api through Vercel (see vercel.json), so the browser
// sees one origin there. Dev talks to Django cross-origin, which keeps
// exercising CORS, credentials and the CSRF header round trip. Code that
// works cross-origin works same-origin; the reverse is not true, and it was
// the reverse that produced a production-only CSRF bug earlier.
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
