# Decisions

Log the decisions that actually shaped this codebase — the ones where a real alternative existed and
you picked one. At least five entries. For each: what you chose, what you rejected, and why. At least
one entry must be a decision you later reversed — say what changed your mind. It can be any entry
below, not necessarily the last one; add a **Later reversed:** line to whichever one it is.

## Decision 1

- **Chose:**
- **Rejected:**
- **Why:**

## Decision 2

- **Chose:**
- **Rejected:**
- **Why:**

## Decision 3

- **Chose:**
- **Rejected:**
- **Why:**

## Decision 4

- **Chose:**
- **Rejected:**
- **Why:**

## Decision 5

- **Chose:**
- **Rejected:**
- **Why:**



### ADR-004 addendum — triggers can be turned off without you noticing

While cleaning up my test data I had to run `ALTER TABLE ... DISABLE TRIGGER`,
since there's no normal way to delete a ledger row. Then the re-enable
statement errored and I didn't notice. Checked `pg_trigger` later and both
triggers were showing `D` — disabled.

What bothered me is that nothing looked wrong. Queries worked, tables were
all there, and the main protection in the whole design was just off.

So two changes:

- The reconciliation job in Phase 8 should also check `tgenabled = 'O'`, not
  just that the balances add up. If a trigger is off, the balances stay fine
  until someone writes something bad, so checking balances alone wouldn't
  catch it in time.

- This makes the separate database role look more worthwhile than I first
  thought. You can switch a trigger off with one statement. You can't switch
  off a role that never had UPDATE or DELETE permission in the first place.

Also affects tests: I can't delete rows in fixture teardown. pytest-django
wraps each test in a transaction and rolls back, and a rollback isn't a
delete, so the triggers don't fire. Only the concurrency tests need
truncation.


### A test that passed while the thing it tested was broken

I had a test asserting `SUM(delta) >= 0` for every item and location — my
"stock never goes negative" check. It passed. Meanwhile the seeded data had a
warehouse whose first ever event was an issue of 2 units, leaving it at −2 for
three weeks.

Both were true at once because a sum doesn't care about order. The service had
validated every movement against the balance *at the time it was recorded*,
and then my seed handed each one an independent random date, so recording
order and date order came apart. Final totals were still correct. Every
intermediate state was not.

The test I should have written replays the ledger in timestamp order and
asserts the running balance never drops below zero. That version fails on the
bad data, and it would also catch a real service-layer ordering bug rather
than just this seeding artefact.

What I take from it: `SUM(delta) >= 0` isn't "no shelf ever went negative", it
is "no shelf is negative right now". I'd named it after the first and only
tested the second, and I only noticed because I happened to look at the dates
on a page.