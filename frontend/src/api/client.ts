/**
 * The only place fetch is called.
 *
 * credentials: "include" is set here once, so every endpoint added later
 * inherits it. Forget it on a single call and that request arrives anonymous,
 * with nothing in the console to explain why -- the quiet failure the
 * cross-origin cookie setup exists to avoid.
 *
 * The CSRF token is read from a cookie and echoed in a header, which is why
 * CSRF_COOKIE_HTTPONLY is False in dev.py. That is deliberate and safe: the
 * token is not a credential, and the session cookie stays HttpOnly.
 */

// Empty in production, where vercel.json proxies /api to the backend on this
// same origin -- so requests go to /api/... and the session cookie is
// first-party. In development it points at the Django dev server. Falling back
// to "" rather than a hardcoded host means a missing value degrades to
// same-origin, which is the safe direction.
const BASE = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {
  // Spelled out longhand rather than as constructor parameter properties.
  // The Vite scaffold enables erasableSyntaxOnly, which allows only
  // TypeScript that is pure annotation -- `public status: number` in a
  // constructor signature emits real assignments, so it is rejected.
  readonly status: number;
  readonly fields?: Record<string, string[]>;
  readonly code?: string;

  constructor(
    status: number,
    message: string,
    fields?: Record<string, string[]>,
    code?: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fields = fields;
    this.code = code;
  }

  /** 401 means log in. 403 means you are logged in and may not do this. */
  get isUnauthenticated() {
    return this.status === 401;
  }

  /** 409: the request was fine, it just conflicts with current state --
   *  not enough stock, item archived. Retrying later could succeed. */
  get isConflict() {
    return this.status === 409;
  }
}

function readCookie(name: string): string {
  const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return match ? decodeURIComponent(match[2]) : "";
}

/** The CSRF token, held in memory.
 *
 * In production the API lives on a different domain than the SPA, so the
 * csrftoken cookie belongs to the API's origin and document.cookie here
 * cannot see it -- the browser sends it with every request, but JavaScript on
 * this page has no access. So the token arrives in the body of
 * /api/auth/csrf/ instead and is remembered here.
 *
 * The cookie is still the fallback, which is what makes same-origin
 * deployments and local development work unchanged.
 */
let csrfToken = "";

export function rememberCsrfToken(token: string) {
  csrfToken = token;
}

/** Fetch a fresh token and remember it.
 *
 * Called on mount and again after login: Django rotates the CSRF secret when
 * a session starts, which silently invalidates whatever token we were holding
 * from before signing in.
 */
export async function primeCsrfToken(): Promise<void> {
  const { csrftoken } = await api.get<{ csrftoken: string }>("/api/auth/csrf/");
  rememberCsrfToken(csrftoken);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);

  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    headers.set("X-CSRFToken", csrfToken || readCookie("csrftoken"));
  }
  // FormData sets its own multipart boundary; overriding Content-Type here
  // would corrupt the body. Only JSON gets the header.
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  // 204 has no body at all, and response.json() would throw on it.
  if (response.status === 204) return undefined as T;

  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    // The backend's exception handler returns {detail, code} and DRF
    // validation errors add per-field arrays alongside them. Splitting the
    // two apart here means a form can highlight the offending input instead
    // of only showing a banner.
    const { detail, code, ...fields } = payload;
    throw new ApiError(
      response.status,
      detail ?? "Something went wrong.",
      Object.keys(fields).length ? fields : undefined,
      code,
    );
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body instanceof FormData ? body : JSON.stringify(body ?? {}),
    }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  // Returns 204 with no body, which request() already handles.
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
