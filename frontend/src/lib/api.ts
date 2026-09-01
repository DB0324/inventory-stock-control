/**
 * The single place the frontend talks to Django.
 *
 * Two things here are not optional, and both follow from the decision in
 * vite.config.ts not to proxy:
 *
 *   1. `credentials: "include"` -- the session lives in a cookie, and the
 *      browser will not attach it to a cross-origin request unless asked.
 *      Leave this out and every authenticated call quietly 403s.
 *   2. The CSRF token on unsafe methods -- Django rejects POST/PUT/PATCH/
 *      DELETE without it. Django sets the csrftoken cookie; we read it back
 *      and echo it in a header, which is why CSRF_COOKIE_HTTPONLY is False
 *      in dev.py. It has to be readable by JavaScript for this to work.
 */

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(^|;\\s*)${name}=([^;]*)`))
  return match ? decodeURIComponent(match[2]) : null
}

export class ApiError extends Error {
  // Written out longhand rather than as constructor parameter properties.
  // The scaffold turns on erasableSyntaxOnly, which restricts us to TypeScript
  // that is pure type annotation -- syntax that emits real code, like `readonly
  // status: number` in a constructor signature, is rejected. Worth keeping:
  // it means the type layer can be stripped without changing behaviour.
  readonly status: number
  readonly body: unknown

  constructor(status: number, body: unknown, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()

  const headers = new Headers(init.headers)
  if (init.body !== undefined) headers.set('Content-Type', 'application/json')

  if (UNSAFE_METHODS.has(method)) {
    const token = readCookie('csrftoken')
    if (token) headers.set('X-CSRFToken', token)
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...init,
    method,
    headers,
    credentials: 'include',
  })

  // 204 has no body, and response.json() would throw on it.
  const payload =
    response.status === 204 ? null : await response.json().catch(() => null)

  if (!response.ok) {
    // Surface the server's own message where there is one. The stock service
    // raises errors that name the actual quantities ("cannot issue 10, only 3
    // on hand"), and throwing that away in favour of "Request failed" would
    // waste the most useful thing the backend says.
    const detail =
      (payload as { detail?: string } | null)?.detail ??
      `${response.status} ${response.statusText}`
    throw new ApiError(response.status, payload, detail)
  }

  return payload as T
}
