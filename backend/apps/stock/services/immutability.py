"""Turning the append-only triggers off, for the very few places allowed to.

Nothing in the application ever uses this. It exists for the seed command,
which has to backdate timestamps that auto_now_add refuses to set, and for
tests that need to simulate history. Both are operations on demo data.

Kept in one module rather than repeated at each call site because it is the
most dangerous code in the project, and because the re-enable must be
impossible to forget.
"""

from contextlib import contextmanager

from django.db import connection

# Every append-only table and the trigger guarding it. Adding a fourth means
# editing this list and nothing else.
IMMUTABLE_TRIGGERS = [
    ("stock_movement", "stock_movement_immutable"),
    ("stock_ledger_entry", "stock_ledger_entry_immutable"),
    ("catalog_item_timeline_event", "catalog_item_timeline_event_immutable"),
]


@contextmanager
def immutability_disabled():
    """Disable the append-only triggers for the duration of the block.

    The finally is not defensive habit. A disabled immutability trigger is the
    worst state to leave a database in, because everything looks healthy and
    nothing is actually protected -- the guarantee is gone and nothing says so.
    """
    with connection.cursor() as cur:
        # Postgres refuses ALTER TABLE on a table with pending trigger events,
        # and Django creates foreign keys as DEFERRABLE INITIALLY DEFERRED, so
        # any insert earlier in this transaction has left a check sitting in
        # the queue. This forces them to run now and empties it. Without it,
        # callers fail with "cannot ALTER TABLE because it has pending trigger
        # events" -- which is easy to mistake for a locking problem.
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        for table, trigger in IMMUTABLE_TRIGGERS:
            cur.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}")
        try:
            yield cur
        finally:
            for table, trigger in IMMUTABLE_TRIGGERS:
                cur.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}")
