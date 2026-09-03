"""Extend the append-only guarantee to the item timeline.

Written by hand on top of an empty `makemigrations --empty` file. Until this
was cleaned up the module defined Migration twice, and only the later
definition took effect -- the migration worked, but by shadowing rather than
by intent, which is not something to leave in a file that runs on deploy.
"""

from django.db import migrations

# The trigger function already exists from stock.0003. This adds the timeline
# to it, so goal 9's "including by managers" is enforced by the database
# rather than by us not having written an edit view.

FORWARD = """
CREATE TRIGGER catalog_item_timeline_event_immutable
  BEFORE UPDATE OR DELETE ON catalog_item_timeline_event
  FOR EACH ROW EXECUTE FUNCTION reject_mutation();
"""

REVERSE = """
DROP TRIGGER IF EXISTS catalog_item_timeline_event_immutable
  ON catalog_item_timeline_event;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0003_itemtimelineevent"),
        ("stock", "0003_immutability_triggers"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]