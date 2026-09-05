# Plan

## How I broke the work into sessions

By phase, not by time. Each phase had a condition that had to be true before
moving on — so instead of "spend two hours on the ledger" it was "don't start
the API until a transfer writes both entries, an overdraw leaves zero rows
behind, and raw SQL can't update a movement."

0. Foundations — repo, settings, database, verify the host
1. Ledger — models, constraints, triggers, `stock_service`, tests
2. Auth and roles
3. Items, categories, movements, audit timeline
4. Search, filter, sort, paginate
5. Alerts and dashboard
6. CSV import and export
7. Client
8. Hardening and deploy

Time-boxing "get the ledger right" does not work. Either the concurrency test
passes or it does not, and there is no useful sense in which it is 80% done at
the two-hour mark.

## What order, and why

Riskiest first: if getting this wrong invalidates everything after it, do it
now.

That put the ledger before anything else. If the transfer sign logic were
wrong, or the negative-stock check did not hold under concurrency, every
feature built on top would inherit the error — silently, because a wrong
quantity does not raise. It just shows a plausible number that is wrong
forever.

Two things I moved earlier than felt natural:

**Verifying the database host before writing a model.** The design depends on
`CREATE TRIGGER`, advisory locks, partial unique indexes and `pg_trgm`. If the
host blocked triggers, the immutability guarantee would need a different
approach entirely — a Phase 0 problem, not a Phase 6 surprise. It took ten
minutes and found a real bug: `pg_trgm` was installed on the dev branch but not
production. Extensions in Neon are per-database, so branching does not carry
across one installed after the branch point.

**The custom user model in migration 0001.** `AUTH_USER_MODEL` cannot be
changed once `auth` has migrated. I hit this directly — ran `migrate` too
early, `auth_user` was created, and I had to reset the Neon branch and redo the
migrations. Two minutes at that point; a rebuild in Phase 3.

Within each phase I wrote the service layer before the API, because the same
operation has several entry points and they all have to enforce the same rules.

## Estimates versus actual

I did not estimate, and I would rather say so than invent numbers afterwards.
The brief suggested a 12-hour budget; I worked to phase gates instead.

**Slower than expected:**

- *Verifying constraints by hand in the SQL editor.* The editor stops at the
  first error, so batching statements meant everything after a failure was
  silently skipped. I kept getting results that looked like constraint failures
  when in fact nothing had run.
- *The migration ordering mistake.* Quick to fix, but it cost a full reset of
  the dev branch.
- *Cross-origin cookies.* Two separate bugs — `localhost` versus `127.0.0.1` in
  development, and third-party cookie blocking in production incognito. Both
  present as "login works, next request is anonymous", which points at
  authentication rather than at the cookie.

**Faster than expected:**

- *The test suite, once it ran against a local Postgres container.* It went
  from 90 seconds against Neon to under a second locally. A 90-second suite is
  one you stop running, and a suite you do not run is worse than none, because
  it gives false confidence.

The most useful thing I did for pace was verifying the host and deploying an
empty app in Phase 0. Both felt like detours; both saved more than they cost.

## What I cut

Working to gates rather than a clock made this "what did I decide not to
build", which is a more honest question.

- **Balance cache table** — ADR-009. Right at scale, wrong now: it recreates
  the second source of truth the design exists to avoid. Documented with a
  measured trigger instead of a guess.
- **Row-level security for location scoping** — stronger in principle, but it
  needs a session variable per request and there is one application writing to
  this database.
- **A background worker** — ADR-008. One process on the free tier, and imports
  are small enough to run synchronously.
- **Hypothesis property tests** — I had declared a `property` marker in
  `pytest.ini` without ever installing the dependency. I removed the marker
  rather than leave something that looked implemented and was not.

## The last pass

After the ten goals were done I went back over the system twice, and both
passes found things that reading the code had not.

The first was "check the edge cases for every goal", which turned up four
untested requirements — per-location availability when the stock is at another
location, archiving preserving history, pagination totals, and the location
plus at-or-below-reorder combination — and one missing feature, the
category-management screen.

The second was production hardening: login rate limiting, CSV injection in the
export, a public health check returning psycopg's connection error verbatim,
and no cache headers on authenticated responses. None of these are in the
brief. All of them are the difference between a demo and something that could
face the internet.

Neither pass was speculative work. Every item was a real defect, and the
health-check one was live on a public endpoint that names the database host,
port, user and password failure in its error text.

## What I would do differently

**Verify the database host before writing anything.** Ten minutes in Phase 0
found the missing `pg_trgm` on production, which would otherwise have appeared
as a failed deploy in Phase 8, while debugging three systems at once.

**Stop doing correctness checks by hand much sooner.** Probing constraints in
the SQL editor let state drift between runs, and at one point I left both
immutability triggers disabled without noticing — the worst state to leave the
database in, because everything looks healthy and nothing is protected. The
pytest version of the same checks runs in under a second and cannot drift.

**Write the query-count tests earlier.** I added them at the end as a guard
against future regressions, and the first run immediately failed on an N+1 that
was already there: the staff screen fetched a user per assignment to render
"granted by". Twenty-four queries where three would do. It had been live for
days and no amount of reading the code had caught it.
