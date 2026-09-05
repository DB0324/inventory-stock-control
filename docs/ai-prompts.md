# AI prompts

---

## 1. The rules I set first

Before any code, I set three standing instructions. They shaped everything
afterwards more than any individual prompt did.

> **Write the files; I run every command myself. Give me the commands as a
> numbered checklist and wait for the output.**

I wanted to see each migration, each test run, each failure with my own eyes.
Handing that over would have meant reviewing code I had never watched execute.
It also caught things — the `pg_trgm` extension missing on the production
branch showed up in output I would never have seen otherwise.

> **Comment like a developer writing for the next developer. Explain why, not
> what. No comment that restates the line below it.**

The result is comments like the one on `sorted()` in `_lock()`, which says
what happens without it rather than "sort the ids".

> **When there is a real choice, tell me the trade-off and recommend one.
> Don't agree with me by default.**

This one needed reinforcing more than once. It is the weakest point of working
this way — see section 6.

---

## 2. Designing the ledger

> Inventory system, Postgres. On-hand must never be stored, always derived.
> Movements are receipt, issue, transfer, adjustment; a transfer moves stock
> between two locations atomically and cannot drive either negative. Propose a
> schema, and for each constraint say what it is protecting against.

**What came back.** The `StockMovement` / `LedgerEntry` split — the event kept
separate from its effects, a transfer being one movement with two entries
summing to zero. Better than my sketch, which modelled transfers as two linked
movements and would have made "did both halves happen?" a question you could
ask.

**What I corrected.** The first version put a `location` on `LedgerEntry` but
left the movement's three location columns unconstrained, so a transfer could
be saved carrying a `location` *and* a source and destination. I added the
`movement_shape_valid` CHECK: a transfer has source and destination and no
location; every other kind is the reverse.

**Why the prompt worked.** It stated the invariant ("never stored, always
derived") as a constraint rather than asking for an opinion, and asked what
each constraint protects against — which is what surfaced the shape problem.

---

## 3. Concurrency

> Two people issue stock from the same location at the same time. Both read the
> balance, both pass the check, both insert. How do I stop that, given there is
> no balance row to lock?

**What came back.** `pg_advisory_xact_lock` keyed on `(item, location)`, and
the reasoning for why `SELECT ... FOR UPDATE` cannot work here: it locks rows
that already exist and does nothing about a concurrent INSERT.

**What I corrected.** The first version locked in whatever order the caller
passed. I asked the follow-up:

> What happens if one thread transfers WH→SF while another transfers SF→WH, on
> the same item, at the same moment?

Deadlock. `sorted()` fixed it. I kept the test that proves it and verified it
by deleting `sorted()` and watching the test hang rather than trusting the
explanation.

**The general form.** Asking "what happens if" against a specific adversarial
scenario found a bug that asking "is this correct?" would not have.

---

## 4. Immutability

> Ledger rows must never be updated or deleted, including by me. Application
> code is not enough — I want it enforced in the database. Write the triggers
> and the migration.

**What came back.** `BEFORE UPDATE OR DELETE` triggers calling a
`reject_mutation()` function, on all three append-only tables.

**What I corrected.** Nothing in the triggers. The problem was downstream: to
reset seed data I had to disable them, and `ALTER TABLE ... DISABLE TRIGGER`
failed with *"cannot ALTER TABLE because it has pending trigger events"*.
Django's foreign keys are `DEFERRABLE INITIALLY DEFERRED`, so
`SET CONSTRAINTS ALL IMMEDIATE` has to come first. Without that, every deploy
that reseeded would have failed.

---

## 5. The prompt that produced something wrong

Required by the brief, and the most useful thing in this file.

> Write a management command that seeds a realistic eight-week demo history 
> receipts, issues, transfers and adjustments across several items and
> locations.

**What came back.** Working code. The dashboard looked right. Every test
passed.

**What was wrong.** It gave each movement an independent random date inside the
window. Movements were validated against the balance at the time they were
*recorded*, but displayed in *date* order so the item timeline showed a
warehouse whose first ever event was an issue of 2 units, sitting at −2 for
three weeks. Final totals were correct, which is exactly why nothing caught it.

I found it by looking at a page, not by running anything.

**What I did.** Asked for the diagnosis, got two candidate causes, and
identified which one mattered. Then I added a constraint of my own:

> Sorting the dates and assigning them in recording order is right, but it
> means the first movement gets the earliest date so make sure the opening
> receipts are included in that sorted assignment rather than pinned
> separately, or you reintroduce the same bug in a different shape.

Two fixes and a new test:

1. Sort the generated dates and assign them in recording order, openings
   included in the sort.
2. A replay test walking the ledger in timestamp order, asserting the running
   balance never drops below zero.

**The real lesson.** My existing invariant, `SUM(delta) >= 0`, is not "no shelf
ever went negative" it is "no shelf is negative right now", because a sum
does not care about order. I had named the test after the first and only tested
the second. Written up in `decisions.md`.

---

## 6. Where I overruled the answer

The three most important moments in the project.

**An unknown location id in the item filter.** I asked what it should do and
was offered "ignore the filter". I rejected it: silently ignoring the filter
shows global quantities labelled as one location's, which is precisely the
quiet wrongness this system exists to prevent. It returns no rows instead, and
the comment in `filters.py` says why.

**Gitignoring `docker-compose.yml`.** I asked for it during the hardening pass
and was pushed back on, correctly: the file holds no secrets the credentials
are `inventory`/`inventory` for a throwaway local test database and ignoring
it would stop a fresh clone running the test suite. I dropped the request.

**Where to enforce location scoping.** Offered row-level security as the
stronger option. I chose the service layer, because RLS needs a session
variable set per request and there is exactly one application writing to this
database. Documented rather than silently skipped.

---

## 7. Prompts that found real defects

The highest-value prompts in the project were not requests for code. They were
requests to *check*.

> Check there is no leakage in the GitHub repo and that everything has been
> pushed.

Found a live Neon database password committed in `.env.example`. I rotated the
credential and scrubbed it from history. Nothing else in the project came close
to this in value.

> I tried all the API query parameters — check them once before we move on.

`?location=not-an-id` was a 500: an uncoerced `int()` raising `ValueError` out
of the ORM. Fixed with `_as_int`, and a test now covers junk ids on both the
location and category filters.

> Check all the edge cases for all ten goals. If it is working fine we move
> ahead.

Four untested requirements per-location availability when the stock is at a
different location, archiving preserving history, pagination totals, and the
location plus at-or-below-reorder combination and one missing feature, the
category-management screen.

> These are the problems I see for a production-grade application: no rate
> limiting on login, CSV injection through `=` and `+`, information leaking
> from the health check, session and role handling, caching.

All real. The health check was returning psycopg's connection error verbatim on
a public endpoint, which names the host, port, user and database.

---

## 8. Prompts that produced hidden wins

> Add query-count tests so a page cannot silently become an N+1.

Written as a guard against future regressions. The first run failed on an N+1
that was **already there**: the staff screen fetched a user per assignment to
render "granted by" twenty-four queries where three would do. It had been
live for days, and reading the code had not caught it.

---

## 9. Where AI was least useful

Anything needing a decision between two defensible options: cache versus
derive, cookie versus token, how strict to be about a stale edit. It argues
both sides well and will agree with whichever way I lean, so the judgement had
to stay mine. The instruction in section 1 *don't agree with me by default* 
helped and did not solve it.

It was most useful for three things: translating a decision I had already made
into code, naming failure modes I had not thought of ("what happens under two
opposing transfers?"), and Postgres specifics I would otherwise have looked up
one at a time.

---

## 10. What I would do differently

**State the invariant before asking for the code.** Every prompt that led with
a constraint "on-hand is never stored", "ledger rows can never be updated"
produced something I kept. Every open-ended one produced something plausible
that disagreed with a decision I had already made.

**Ask "what happens if" more often.** Two of the three worst bugs were found by
a follow-up question about a specific scenario, not by review.

**Verify claims by breaking them.** The deadlock fix was believable. I deleted
`sorted()` and watched the test hang, and only then trusted it. That habit
should have started earlier the seed-data bug survived because I trusted a
test whose name did not match what it asserted.
