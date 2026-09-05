# Decisions

Numbering matches the ADR references in the code comments.

## ADR-001 — Append-only ledger, on-hand always derived

- **Chose:** `StockMovement` (the event) plus `LedgerEntry` (the effect).
  On-hand is `SUM(delta)`, computed on every read. There is no quantity column
  anywhere.
- **Rejected:** A `quantity` column on `Item`, updated on each movement.
- **Why:** A stored quantity is a second source of truth. The moment one code
  path forgets to update it, the number is wrong forever and nothing raises an
  error — it just shows a plausible figure. Deriving it means the balance
  cannot disagree with the history, because it *is* the history.

## ADR-002 — Advisory locks, not row locks

- **Chose:** `pg_advisory_xact_lock` on each `(item, location)` pair, acquired
  in sorted order.
- **Rejected:** `SELECT ... FOR UPDATE`.
- **Why:** There is no row holding "item 42's balance at WH" — that is the
  whole design — so there is nothing for `FOR UPDATE` to lock. It locks rows
  that already exist and does nothing to stop a concurrent INSERT. Sorting the
  keys is what stops two opposing transfers deadlocking. The transaction-scoped
  variant releases on commit or rollback, so a crash cannot wedge a pair.

## ADR-003 — Role as a column, not Django Groups

- **Chose:** A `role` column with two values.
- **Rejected:** `django.contrib.auth` Groups and permissions.
- **Why:** The two roles are fixed by the brief and never user-configurable.
  A column is explicit, greppable and joinable. Groups would be right if roles
  were data.

## ADR-004 — Immutability enforced by the database

- **Chose:** Three layers — no update or delete code path, an `ImmutableModel`
  base that raises on `save()`/`delete()`, and `BEFORE UPDATE OR DELETE`
  triggers in Postgres.
- **Rejected:** Enforcing it in application code alone.
- **Why:** Goal 4 says the ledger can never be changed. Application-only
  enforcement holds until someone opens psql or writes a management command.
  The trigger holds against everything, including my own future mistakes.

## ADR-005 — Rules live in the service layer

- **Chose:** All business rules in `apps/stock/services/`, with views calling
  them.
- **Rejected:** Validation in serializers and views.
- **Why:** The same operation has three entry points — the API, CSV import and
  the seed command. Rules in a view mean writing the negative-stock check three
  times and getting two of them right.

## ADR-006 — Commit to PostgreSQL

- **Chose:** Functional unique indexes, partial indexes, CHECK constraints,
  triggers, advisory locks and `pg_trgm`.
- **Rejected:** Staying database-agnostic.
- **Why:** Half the guarantees in this design are only expressible in a real
  database. Portability would have cost the immutability triggers, which are
  the point.

## ADR-007 — Session cookie auth, served same-origin

- **Chose:** Django session cookie, `HttpOnly`, with the CSRF token echoed in
  `X-CSRFToken`.
- **Rejected:** JWTs in `localStorage`.
- **Why:** A token JavaScript can read is a token XSS can steal. An `HttpOnly`
  cookie cannot be read by script at all, and Django's session handling is
  already written and tested.
- **Later reversed:** The frontend originally called the Render host directly,
  cross-origin, with `SameSite=None; Secure` and a CORS allowlist. It worked in
  a normal window and failed completely in incognito: the cookie was
  third-party, Chrome dropped it, login succeeded and the next request arrived
  anonymous. The fix was to stop being cross-origin at all — a Vercel rewrite
  proxies `/api/*` to Render, so the cookie is first-party. What changed my
  mind was that no amount of correct cookie configuration survives a browser
  that refuses third-party cookies on principle.

## ADR-008 — No background worker

- **Chose:** CSV imports run synchronously inside the request.
- **Rejected:** A queue and a worker process.
- **Why:** The free tier gives one process, and an undeployable queue is worse
  than none. Imports are small enough that this holds. It stops holding at file
  sizes where the request would time out, and that is when to revisit it.

## ADR-009 — No balance cache table

- **Chose:** Compute `SUM(delta)` on every read.
- **Rejected:** A materialised balance-per-(item, location) table.
- **Why:** It is the right answer at scale and the wrong one now. It
  reintroduces the second source of truth ADR-001 exists to avoid, and every
  write path has to maintain it. Deferred with a measured trigger — item-list
  p95 over 300 ms, or 100k ledger entries on a single item — rather than a
  guess.

## ADR-010 — Four movement endpoints, not one

- **Chose:** Separate routes and serializers for receipt, issue, transfer and
  adjustment.
- **Rejected:** One polymorphic `/api/movements/` taking a `kind`.
- **Why:** Each kind has different required fields. A single serializer with
  branching validation is where required-field bugs hide — and the CHECK
  constraint on movement shape says the same thing at the database level.

## ADR-011 — No self-service sign-up

- **Chose:** Managers create accounts; access is revoked by deactivating.
- **Rejected:** A public registration form.
- **Why:** In this system the user list *is* the permissions list. Any account,
  even one with no locations assigned, can read the whole catalogue and every
  stock position. Deactivation rather than deletion because movements point at
  the person who recorded them, and a ledger entry with no author is worse than
  no ledger.

## ADR-012 — Optimistic locking on item edits

- **Chose:** A `version` column, sent back as `expected_version` and checked
  under a row lock. A stale save returns 409.
- **Rejected:** Last-write-wins, and pessimistic row locking.
- **Why:** Two managers with the same item open used to mean the second save
  silently discarded the first. The timeline recorded both, so the loss was
  auditable — but nobody was told. Pessimistic locking would mean holding a row
  lock across a human filling in a form, which is worse than the problem.

## ADR-013 — Two login rate limits, not one

- **Chose:** A per-account limit (5/min, keyed on the submitted email) and a
  looser per-address limit (30/min), backed by a database cache.
- **Rejected:** A single per-IP limit; local-memory caching.
- **Why:** Each limit stops an attack the other does not. Per-IP alone leaves
  a botnet a thousand fresh budgets against one account; per-account alone
  lets one address work through an email list. The per-IP one is the looser of
  the two because it depends on reading the right position in
  `X-Forwarded-For` behind two proxies — if that is wrong every request looks
  like the proxy, and a tight limit would lock out all users at once. The
  per-account limit keys on the request body and cannot be wrong that way.
  LocMemCache was rejected because it is per-process: with several gunicorn
  workers "five attempts" silently becomes five per worker.

## ADR-014 — `Cache-Control: no-store` on the whole API

- **Chose:** Blanket `no-store` on every `/api/` response, via middleware.
- **Rejected:** Per-view cache headers.
- **Why:** Every API response is specific to the signed-in user. Without this,
  signing out and pressing Back renders the previous user's stock positions
  from the browser cache without a request ever reaching the server. Blanket
  rather than per-view because the endpoint someone forgets to annotate is
  exactly the one that leaks, and the client already caches in memory through
  TanStack Query, so nothing here costs a round trip that was being saved.

---

## Addendum to ADR-004 — triggers can be turned off without you noticing

While cleaning up my test data I had to run `ALTER TABLE ... DISABLE TRIGGER`,
since there is no normal way to delete a ledger row. Then the re-enable
statement errored and I did not notice. Checking `pg_trigger` later showed both
triggers as `D` — disabled.

What bothered me is that nothing looked wrong. Queries worked, tables were all
there, and the main protection in the whole design was simply off.

Two consequences:

- A reconciliation check should also assert `tgenabled = 'O'`, not just that
  balances add up. If a trigger is off, balances stay fine until someone writes
  something bad, so checking balances alone would not catch it in time.
- A separate database role without UPDATE or DELETE permission looks more
  worthwhile than I first thought. You can switch a trigger off with one
  statement. You cannot switch off a permission that was never granted.

It also constrains the tests: fixtures cannot delete rows. pytest-django wraps
each test in a transaction and rolls it back, and a rollback is not a delete,
so the triggers do not fire. Only the concurrency tests, which need real
commits, require truncation.

## Addendum — a test that passed while the thing it tested was broken

I had a test asserting `SUM(delta) >= 0` for every item and location — my
"stock never goes negative" check. It passed. Meanwhile the seeded data had a
warehouse whose first ever event was an issue of 2 units, leaving it at −2 for
three weeks.

Both were true at once because a sum does not care about order. The service had
validated every movement against the balance *at the time it was recorded*, and
then the seed handed each movement an independent random date, so recording
order and date order came apart. Final totals were correct. Every intermediate
state was not.

The test I should have written replays the ledger in timestamp order and
asserts the running balance never drops below zero. That version fails on the
bad data, and it would also catch a real service-layer ordering bug rather than
just a seeding artefact.

What I take from it: `SUM(delta) >= 0` is not "no shelf ever went negative", it
is "no shelf is negative right now". I had named it after the first and only
tested the second.
