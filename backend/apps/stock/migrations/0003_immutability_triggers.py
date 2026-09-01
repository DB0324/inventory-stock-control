"""Make the ledger append-only at the database, not just in Python.

Goal 4 says a recorded movement can never be changed or removed. Goal 9 says
the same of the timeline, "including by managers". ImmutableModel in models.py
covers the ordinary paths, but Model.save() is never called by
queryset.update(), by a bulk delete, by a raw SQL statement, or by anyone
poking at the database with psql. So the honest answer to "what actually stops
a mutation?" has to be a trigger -- everything above it is a courtesy that
returns a nicer error message.
"""

from django.db import migrations

FORWARD = """
CREATE OR REPLACE FUNCTION reject_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Table % is append-only (attempted %)', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER stock_movement_immutable
  BEFORE UPDATE OR DELETE ON stock_movement
  FOR EACH ROW EXECUTE FUNCTION reject_mutation();

CREATE TRIGGER stock_ledger_entry_immutable
  BEFORE UPDATE OR DELETE ON stock_ledger_entry
  FOR EACH ROW EXECUTE FUNCTION reject_mutation();
"""

# Written out properly rather than left as irreversible, so that a bad deploy
# can roll back without a human editing production by hand at the worst
# possible moment. Order matters: triggers first, then the function they use.
REVERSE = """
DROP TRIGGER IF EXISTS stock_ledger_entry_immutable ON stock_ledger_entry;
DROP TRIGGER IF EXISTS stock_movement_immutable ON stock_movement;
DROP FUNCTION IF EXISTS reject_mutation();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("stock", "0002_stockmovement_ledgerentry_and_more"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
