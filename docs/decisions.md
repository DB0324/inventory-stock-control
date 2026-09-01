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