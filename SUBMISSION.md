# Submission

## Links

- **GitHub repository:** https://github.com/DB0324/inventory-stock-control
- **Live application:** https://inventory-stock-control.vercel.app
- **API:** https://inventory-stock-control-ml03.onrender.com

## Notes for the reviewer

Both the API (Render free tier) and the database (Neon, scale-to-zero) sleep
when idle. The first request after a quiet period can take 30–60 seconds while
both wake up. A slow first load is not a broken deployment.

There is no sign-up link on the login page. That is deliberate: an account is
read access to every stock position in the system, so managers create accounts
under **People**. See ADR-011.

## Demo credentials

| Role | Email | Password |
|------|-------|----------|
| Inventory manager | manager@inventory.local | `Demo@123` |
| Warehouse staff | staff@inventory.local | `Demo@123` |

These are demo-only accounts on a demo deployment; the data is fabricated. Sign
in as the manager to see everything, or as staff to see the same system with
writes restricted to the warehouse.

## Stack

| Layer | What I used | Why |
|-------|-------------|-----|
| Frontend | React 19, TypeScript, Vite, Tailwind 4, TanStack Query | Server state and local state are different problems; TanStack Query handles caching and invalidation so I never hand-roll it |
| Backend | Django 6, Django REST Framework | The auth, migrations and admin are already written and tested; DRF gives permissions and pagination without inventing either |
| Database | PostgreSQL 17 (Neon) | Half the guarantees here — triggers, functional indexes, partial indexes, advisory locks, `pg_trgm` — only exist in a real database |
| Hosting | Vercel (client), Render (API), Neon (database) | Free tiers, and Vercel rewrites `/api` to Render so the session cookie stays first-party |

## Goal checklist

| # | Goal | Status | Notes |
|---|------|--------|-------|
| 1 | Accounts and roles | Done | Enforced in the service layer, not just the views, so CSV import and the seed command obey the same rules. Every permission test hits the URL directly |
| 2 | Items | Done | Archive blocks new movements and keeps history. Categories are a manager-maintained list with case-insensitive uniqueness |
| 3 | Stock movements | Done | Four kinds, `recorded_by` on every one, source and destination on transfers, full history in order |
| 4 | The stock ledger | Done | No quantity column anywhere. Immutability in three layers ending in Postgres triggers. Transfers are two entries in one transaction, checked under an advisory lock |
| 5 | Location assignment | Done | Explicit join table carrying who granted it and when. Revoking keeps the movements already recorded |
| 6 | Finding items | Done | All filtering, sorting and pagination in SQL. Sort is an allow-list; unknown ids return nothing rather than an unfiltered list |
| 7 | Bulk import and export | Done | Savepoint per row, so one bad line costs only that line. Errors name the spreadsheet line number |
| 8 | A dashboard | Done | Four headline tiles, on-hand by category and location, eight-week receipt/issue chart with empty weeks zero-filled |
| 9 | History you cannot rewrite | Done | Created, field changes with old and new values, and notes in one timeline. No write route, and triggers reject `UPDATE`/`DELETE` from raw SQL |
| 10 | Low-stock alerts | Done | Count badge in the nav, manager dismissal, and the dismissal lapses on recovery so the alert genuinely returns on a second fall |

**Known limitation:** the item list's location filter offers every location to
staff, not only their assigned ones. It is a read-only view and the write path
is properly scoped, so nothing leaks that a staff member could act on.

**Tests:** 222, against PostgreSQL 17 in Docker. Includes six real-thread
concurrency tests, four query-count tests that pin query shape rather than
speed, and a hardening file covering login rate limits, session behaviour and
response headers.

## Beyond the brief

None of this is in the ten goals; all of it is the gap between a demo and
something that could face the internet. Covered by `test_hardening.py`.

- **Login rate limiting.** Five attempts a minute per account and thirty per
  address. Two limits rather than one, because each stops an attack the other
  does not (ADR-013).
- **CSV injection.** The export prefixes any cell starting with `=`, `+`, `-`,
  `@`, tab or carriage return, so a manager-typed item name cannot become a
  live formula in someone's spreadsheet.
- **Information disclosure.** `/healthz/` used to return psycopg's connection
  error verbatim on a public, unauthenticated endpoint — which names the host,
  port, user and database. It now returns `{"status": "error"}` and logs the
  detail.
- **Cached authenticated data.** `Cache-Control: no-store` on every `/api/`
  response. Without it, signing out and pressing Back re-renders the previous
  user's stock positions from cache, without a request reaching the server.
- **Live privileges.** Role and active status are read from the database on
  every request rather than copied into the session, so a demotion or a
  deactivation applies to the next request rather than the next sign-in.
- **Optimistic locking on item edits.** Two managers editing the same item used
  to mean the second save silently discarded the first; it now returns 409.

## How much time did I spend?

I worked to phase gates rather than a clock, so I do not have an hour count I
would trust. See `docs/plan.md` for the phases and what ran long.

## What I would do next, with another 12 hours

1. **Verify NUM_PROXIES against a real X-Forwarded-For.** The per-IP login
   limit reads the client address from that header, and the correct position
   in it is a property of the deployment. It is set from an environment
   variable and the per-account limit does not depend on it, so a wrong value
   weakens one layer rather than breaking login — but it should be confirmed
   from the logs rather than assumed.
2. **Reconciliation job.** A scheduled check that ledger balances agree with
   themselves *and* that the immutability triggers are still enabled. I once
   left both disabled without noticing, and nothing looked wrong.
3. **Invite links instead of manager-set passwords.** A single-use token
   emailed to the new user, so the password never passes through a third
   person.
4. **Scope the item list's location filter to assigned locations for staff.**
5. **A read-only database role for the web process**, without UPDATE or DELETE
   on the append-only tables. A trigger can be switched off with one statement;
   a permission that was never granted cannot.

## What I am least happy with

The seed command. It is the least-loved code in the repo and it caused the
worst bug, a demo history whose dates and recording order disagreed, showing a
warehouse at −2 units for three weeks. Everything else in the system has one
place where a rule is enforced; the seed command reimplements a plausible
history alongside them, and that duplication is exactly where it went wrong.

Second, the frontend has no tests. The backend has 222 and the client has type
checking and lint. The riskiest client logic, resetting pagination on a filter
change and reloading the form after an edit conflict, is exactly the kind of
thing a couple of component tests would pin, and I would write those before
adding another page.
