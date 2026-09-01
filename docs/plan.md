# Plan

Answer each of these, in your own words.

- How did you break the work into sessions?
- What order did you build in, and why that order?
- What did you estimate versus what it actually took?
- What did you cut when you ran short?


# Plan

## How did you break the work into sessions?

Not by time. I worked in phases, each with a condition that had to be true
before moving on. So instead of "spend two hours on the ledger" it was "don't
start the API until a transfer writes both entries, an overdraw leaves zero
rows behind, and raw SQL can't update a movement."

The phases:

0. Foundations — repo, settings, database, verify the host
1. Ledger — models, constraints, triggers, stock_service, tests
2. Auth and roles
3. Items, categories, movements, audit timeline
4. Search, filter, sort, paginate
5. Alerts and dashboard
6. CSV import and export
7. Client
8. Hardening and deploy

I did it this way because time-boxing something like "get the ledger right"
doesn't work. Either the concurrency test passes or it doesn't, and there's no
useful sense in which it's 80% done at the two-hour mark.

## What order did you build in, and why that order?

Riskiest first. The rule was: if getting this wrong invalidates everything
after it, do it now.

That put the ledger before anything else. If the transfer sign logic were
wrong, or the negative-stock check didn't hold under concurrency, every
feature built on top would inherit the error — and silently, because a wrong
quantity doesn't raise an exception. It just shows a plausible number that's
wrong forever.

Two things I moved earlier than felt natural:

**Verifying the database host before writing a model.** The design depends on
`CREATE TRIGGER`, advisory locks, partial unique indexes and `pg_trgm`. If the
host blocked triggers, the immutability guarantee would need a completely
different approach, and that's a Phase 0 problem rather than something to find
out in Phase 6. Took ten minutes and turned up a real bug: `pg_trgm` was
installed on the dev branch but not production. Extensions in Neon are
per-database, so branching doesn't carry across one installed after the branch
point. That would have surfaced as a failed deploy much later.

**The custom User model in migration 0001.** Django's `AUTH_USER_MODEL` can't
be changed once `auth` has migrated. I hit this directly — ran `migrate` too
early, `auth_user` got created, and I had to reset the Neon branch and redo
the migrations. Two minutes at that point. A rebuild if I'd found it in
Phase 3.

Within each phase I wrote the service layer before the API, because the same
operation has several entry points (web, CSV import, seed command) and they
all have to enforce the same rules. Putting those rules in the views would
have meant writing the negative-stock check three times and getting two of
them right.

## What did you estimate versus what it actually took?

I didn't estimate, and I'd rather say that than invent numbers afterwards. The
brief suggested a 12-hour budget; I worked to phase gates instead, because
"the ledger is correct" isn't something you can schedule.

What I can say is which parts took longer than I expected:

- **Verifying the constraints by hand in the SQL editor.** The editor stops at
  the first error, so batching statements meant everything after a failure was
  silently skipped. I kept getting results that looked like the constraints
  had failed when actually nothing had run. Took a few attempts to work out
  the harness was the problem, not the schema.
- **The migration ordering mistake.** Not long to fix, but it cost a full
  reset of the dev branch and a re-run of every migration.
- **[add anything else that slowed you down]**

Quicker than expected:

- **The test suite, once it ran against a local Postgres container.** It went
  from 90 seconds against Neon to under a second locally. That completely
  changed how often I ran it — a 90-second suite is one you stop running, and
  a suite you don't run is worse than none because it gives false confidence.
- **[add anything else]**

The most useful thing I did for pace was verifying the host and deploying an
empty app in Phase 0. Both felt like detours. Both saved more than they cost.

## What did you cut when you ran short?

Since I worked to gates rather than a clock, this became "what did I decide
not to build," which is a different question but a more honest one.

- **Balance cache table.** It's the right answer at scale and the wrong one
  now. It creates a second source of truth for the one number the spec says
  must have only one, and every write path has to maintain it. I documented
  the escalation path and a measured trigger instead — item list p95 over
  300ms — rather than guessing when it's needed.
- **Row-level security for location scoping.** Technically stronger than
  checking in the service layer, but it needs a session variable set per
  request and makes seeding awkward, and there's exactly one application
  writing to this database.
- **Hypothesis property tests.** I'd declared a `property` marker in
  `pytest.ini` without ever installing the dependency. I removed the marker
  rather than leave something that looked implemented and wasn't.
- **[anything else you dropped]**

One decision I reversed: I originally ruled out a background worker, because
the free tier gives you a single process and an undeployable queue is worse
than no queue. That was right under a time budget. Once the budget went away
it stopped being right — synchronous CSV import has a hard ceiling, and
holding an advisory lock across file I/O isn't safe anyway. Written up as
ADR-008.

## What I'd do differently

Two things.

I'd verify the database host before writing anything, on any project, not just
this one. Ten minutes in Phase 0 found the missing `pg_trgm` on production.
That would otherwise have shown up as a failed deploy in Phase 8, when I'd be
debugging three systems at once and unable to tell which was broken.

And I'd stop doing correctness checks by hand much sooner. I spent a while
probing constraints in the SQL editor, and the state kept drifting between
runs because there's no setup or teardown. At one point I left both
immutability triggers disabled without noticing — which is the worst state to
leave the database in, because everything looks healthy and nothing is
protected. The pytest version of the same checks runs in under a second and
can't drift.