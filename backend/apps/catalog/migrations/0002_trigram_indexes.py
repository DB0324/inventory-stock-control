"""Trigram indexes so substring search does not degrade into a table scan.

Goal 6 wants search by name and SKU done on the server, and "contains" search
means ILIKE '%term%'. A leading wildcard makes a normal B-tree index useless,
so without these GIN indexes every keystroke in the search box reads the whole
item table. Fine with 50 rows, not fine later -- and the index is cheap enough
that adding it now is easier than diagnosing it in six months.
"""

from django.db import migrations

FORWARD = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX item_name_trgm ON catalog_item USING GIN (name gin_trgm_ops);
CREATE INDEX item_sku_trgm  ON catalog_item USING GIN (sku  gin_trgm_ops);
"""

# The extension is deliberately left in place on reverse. Other things may
# come to depend on it, and dropping a shared extension to undo two indexes
# is a bigger hammer than the situation calls for.
REVERSE = """
DROP INDEX IF EXISTS item_sku_trgm;
DROP INDEX IF EXISTS item_name_trgm;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
