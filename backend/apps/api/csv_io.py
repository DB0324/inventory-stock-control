"""Bulk import and export (goal 7).

The requirement that shapes everything here: an import must report exactly
which rows failed and why, while still importing every row that was valid.
One bad line in a hundred is a typo, not a reason to reject the file and make
someone find it by bisection.

That means each row gets its own savepoint. Without one, the first
IntegrityError marks the whole transaction as broken and every subsequent
query fails with "current transaction is aborted" -- so a single bad row would
take the ninety-nine good ones with it, which is exactly the behaviour the
brief rules out.

Imports go through the same services as the UI. A CSV that could write states
the API refuses would be a second, weaker door into the ledger.
"""

import csv
import io

from django.db import transaction
from django.db.models import Sum

from apps.catalog.models import Category, Item
from apps.catalog.services import timeline_service as ts
from apps.stock.models import LedgerEntry, Location
from apps.stock.services import stock_service as ss

ITEM_COLUMNS = ["sku", "name", "category", "unit_of_measure", "reorder_level"]
RECEIPT_COLUMNS = ["sku", "location", "quantity"]


class CsvFormatError(Exception):
    """The file itself is unusable -- not one bad row, but no usable rows."""


def _read(file, required):
    """Decode and validate the header before touching the database.

    A missing column is a property of the file, not of any row, so it is
    reported once rather than repeated against every line.
    """
    try:
        text = file.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvFormatError(
            "The file is not valid UTF-8. Re-export it as UTF-8 CSV."
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise CsvFormatError("The file is empty.")

    headers = {name.strip().lower() for name in reader.fieldnames if name}
    missing = [column for column in required if column not in headers]
    if missing:
        raise CsvFormatError(
            f"Missing column(s): {', '.join(missing)}. "
            f"Expected at least: {', '.join(required)}."
        )
    return reader


def _clean(row):
    """Lowercase the keys and strip the values.

    Spreadsheets add trailing spaces and inconsistent header case constantly,
    and neither is a mistake worth failing someone's import over.
    """
    return {
        (key or "").strip().lower(): (value or "").strip()
        for key, value in row.items()
    }


def import_items(*, file, actor):
    reader = _read(file, ITEM_COLUMNS)
    created = updated = 0
    errors = []

    # Fetched once. Doing this per row would be a query per line, and the
    # categories cannot change during the import.
    categories = {c.name.lower(): c for c in Category.objects.all()}

    # enumerate from 2: line 1 is the header, so this matches what the person
    # sees in their spreadsheet. Reporting a zero-based row index would make
    # them count.
    for line, raw in enumerate(reader, start=2):
        row = _clean(raw)
        try:
            # Each row in its own savepoint -- see the module docstring.
            with transaction.atomic():
                sku = row["sku"].upper()
                if not sku:
                    raise ValueError("sku is required.")

                category = categories.get(row["category"].lower())
                if category is None:
                    raise ValueError(
                        f"Unknown category {row['category']!r}. "
                        f"Categories are a maintained list; create it first."
                    )

                try:
                    reorder = int(row["reorder_level"] or 0)
                except ValueError:
                    raise ValueError(
                        f"reorder_level {row['reorder_level']!r} is not a whole number."
                    ) from None
                if reorder < 0:
                    raise ValueError("reorder_level cannot be negative.")

                fields = {
                    "name": row["name"],
                    "category": category,
                    "unit_of_measure": row.get("unit_of_measure") or "EA",
                    "reorder_level": reorder,
                    "description": row.get("description", ""),
                }
                if not fields["name"]:
                    raise ValueError("name is required.")

                item = Item.objects.filter(sku=sku).first()
                if item is None:
                    item = Item.objects.create(sku=sku, **fields)
                    ts.record_created(item=item, actor=actor)
                    created += 1
                else:
                    # An import that re-sends a row is updating, not
                    # duplicating -- and the change lands in the timeline the
                    # same as an edit through the UI would.
                    before = ts.snapshot(item)
                    for key, value in fields.items():
                        setattr(item, key, value)
                    item.save()
                    ts.record_changes(item=item, actor=actor, before=before)
                    updated += 1
        except Exception as exc:
            errors.append({"row": line, "sku": row.get("sku", ""), "error": str(exc)})

    return {
        "created": created,
        "updated": updated,
        "failed": len(errors),
        "errors": errors,
    }


def import_receipts(*, file, actor):
    reader = _read(file, RECEIPT_COLUMNS)
    recorded = 0
    errors = []

    locations = {loc.code.upper(): loc for loc in Location.objects.all()}

    for line, raw in enumerate(reader, start=2):
        row = _clean(raw)
        try:
            with transaction.atomic():
                item = Item.objects.filter(sku=row["sku"].upper()).first()
                if item is None:
                    raise ValueError(f"No item with SKU {row['sku']!r}.")

                location = locations.get(row["location"].upper())
                if location is None:
                    raise ValueError(f"No location with code {row['location']!r}.")

                try:
                    quantity = int(row["quantity"])
                except ValueError:
                    raise ValueError(
                        f"quantity {row['quantity']!r} is not a whole number."
                    ) from None

                # Through the service, so archived items, location assignment
                # and the quantity rules all apply exactly as they do to a
                # movement recorded by hand.
                ss.record_receipt(
                    actor=actor,
                    item=item,
                    location=location,
                    quantity=quantity,
                    note=row.get("note", ""),
                )
                recorded += 1
        except Exception as exc:
            errors.append({"row": line, "sku": row.get("sku", ""), "error": str(exc)})

    return {"recorded": recorded, "failed": len(errors), "errors": errors}


def export_stock_position():
    """Every item's on-hand quantity by location, as CSV rows.

    Yielded rather than accumulated, so the response streams instead of
    building the whole file in memory.

    Only pairs with ledger history appear. A row saying an item holds zero at
    a location it has never been near is noise, and with a handful of
    locations the full cross product grows faster than the useful part of it.
    """
    yield ["sku", "name", "category", "location", "location_name", "on_hand"]

    rows = (
        LedgerEntry.objects.values(
            "item__sku",
            "item__name",
            "item__category__name",
            "location__code",
            "location__name",
        )
        .annotate(on_hand=Sum("delta"))
        .order_by("item__sku", "location__code")
    )
    for row in rows:
        yield [
            row["item__sku"],
            row["item__name"],
            row["item__category__name"],
            row["location__code"],
            row["location__name"],
            row["on_hand"],
        ]
