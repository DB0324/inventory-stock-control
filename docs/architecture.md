# Architecture

## The moving pieces

| Piece | What it is | Where it runs |
|---|---|---|
| Client | React 19 + TypeScript SPA, built by Vite | Vercel (static) |
| API | Django 6 + Django REST Framework | Render (gunicorn) |
| Database | PostgreSQL 17 | Neon |
| Test database | PostgreSQL 17 in Docker | Local only |

The client talks to the API over JSON. There is no server-side rendering and
no shared code between the two.

Requests reach the API at `/api/...` on the Vercel domain, and a Vercel rewrite
proxies them to Render. The browser therefore sees a single origin, which is
what keeps the session cookie first-party (ADR-007).

Auth is a Django session cookie: `HttpOnly`, so JavaScript cannot read it, with
a CSRF token echoed back in the `X-CSRFToken` header.

## Hardening

Applied across the whole API rather than endpoint by endpoint, because the
endpoint someone forgets to annotate is the one that leaks.

| Concern | How |
|---|---|
| Brute-forced logins | Two throttles: 5/min per account, 30/min per address. Both needed — see ADR-013 |
| Cached authenticated data | `Cache-Control: no-store` and `Vary: Cookie` on every `/api/` response, via middleware |
| CSV injection | Export prefixes any cell starting with `= + - @ tab CR`, so a spreadsheet reads it as text rather than a formula |
| Information disclosure | `/healthz/` returns a bare `{"status": "error"}`; the psycopg detail, which names the host, port, user and database, goes to the log |
| Stale privileges | Role and active status are read from the database on every request, never copied into the session, so a demotion or a deactivation applies to the next request |

The throttle counters live in a **database** cache rather than local memory.
LocMemCache is per-process, so with several gunicorn workers "five attempts"
silently becomes five per worker — a rate limit that only looks like one.

## Layers inside the API

```
HTTP  →  views + serializers      permissions, request shape, status codes
      →  services                 all business rules
      →  models + constraints     shape the database will not allow to break
```

Middleware sits outside all three and only adds response headers.

The service layer is the important one. Movements can be recorded from the web
UI, from a CSV import, and from the seed command, and every rule — negative
stock, archived items, location assignment, mandatory adjustment reasons — is
enforced in `apps/stock/services/stock_service.py` rather than in a view. Rules
written in a view get written three times and two of them are wrong.

## Request path: recording a transfer

1. `POST /api/movements/transfer/` from the browser, with the session cookie
   and `X-CSRFToken`.
2. Vercel rewrites `/api/*` to the Render host.
3. Django authenticates the session; `CanRecordMovement` checks the user is
   signed in.
4. `TransferInputSerializer` validates the shape and rejects source ==
   destination.
5. `stock_service.record_transfer` opens a transaction and:
   - refuses if the item is archived;
   - refuses if the user is not assigned to *both* locations (managers skip
     this by role);
   - takes `pg_advisory_xact_lock` on each `(item, location)` pair, in sorted
     order so two opposing transfers cannot deadlock;
   - reads the source balance as `SUM(delta)` and refuses if it is short;
   - inserts one `StockMovement` and two `LedgerEntry` rows, `-q` and `+q`.
6. The transaction commits. Either both entries exist or neither does.
7. The response carries the new balances; the client invalidates its cached
   queries for that item.

An overdraw returns **409**, not 400 — the request was well formed and the
same request could succeed once stock arrives.

## What I decided not to build

- **A stored quantity column or balance cache.** It is the right answer at
  scale and the wrong one here: it creates a second source of truth for the one
  number that must have only one. Deferred with a measured trigger (ADR-009).
- **Self-service registration.** An account is read access to every stock
  position in the business, so accounts are created by a manager (ADR-011).
- **A background worker.** The free tier gives one process; CSV imports run
  synchronously and are small enough for that to be fine.
- **Row-level security for location scoping.** Stronger in principle, but it
  needs a session variable per request and there is exactly one application
  writing to this database.
- **JWTs.** A session cookie that JavaScript cannot read is simpler and safer
  here than a token in `localStorage`.
