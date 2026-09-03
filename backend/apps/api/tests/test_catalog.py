"""Tests A-07 to A-14 plus the catalogue contract.

Every permission test hits the URL directly with APIClient. Asserting that a
button is hidden does not satisfy goal 1.
"""

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Item
from apps.stock.services import stock_service as ss


@pytest.fixture
def client():
    return APIClient()


# --- Manager-only writes --------------------------------------------------

def test_staff_cannot_create_item(client, staff_wh, category):
    client.force_authenticate(staff_wh)
    response = client.post("/api/items/", {
        "sku": "X-1", "name": "Nope", "unit_of_measure": "EA",
        "reorder_level": 5, "category": category.id,
    }, format="json")
    assert response.status_code == 403
    assert not Item.objects.filter(sku="X-1").exists()


def test_staff_cannot_create_category(client, staff_wh):
    client.force_authenticate(staff_wh)
    assert client.post("/api/categories/", {"name": "Nope"},
                       format="json").status_code == 403


def test_staff_cannot_create_location(client, staff_wh):
    client.force_authenticate(staff_wh)
    assert client.post("/api/locations/", {"code": "X", "name": "Nope"},
                       format="json").status_code == 403


def test_staff_cannot_archive_item(client, staff_wh, item):
    client.force_authenticate(staff_wh)
    assert client.post(f"/api/items/{item.id}/archive/").status_code == 403


def test_staff_can_read_items(client, staff_wh, item):
    """Staff need the list to record movements against."""
    client.force_authenticate(staff_wh)
    assert client.get("/api/items/").status_code == 200


def test_manager_can_create_item(client, manager, category):
    client.force_authenticate(manager)
    response = client.post("/api/items/", {
        "sku": "B-200", "name": "Washer", "unit_of_measure": "EA",
        "reorder_level": 20, "category": category.id,
    }, format="json")
    assert response.status_code == 201


# --- Timeline is written automatically ------------------------------------

def test_creating_an_item_writes_a_timeline_event(client, manager, category):
    client.force_authenticate(manager)
    response = client.post("/api/items/", {
        "sku": "C-300", "name": "Nut", "unit_of_measure": "EA",
        "reorder_level": 10, "category": category.id,
    }, format="json")
    item = Item.objects.get(pk=response.data["id"])
    assert item.timeline.get().event_type == "CREATED"


def test_editing_an_item_records_old_and_new(client, manager, item):
    client.force_authenticate(manager)
    client.patch(f"/api/items/{item.id}/", {"name": "Renamed"}, format="json")
    event = item.timeline.get(field_name="name")
    assert event.old_value == "Hex bolt M8"
    assert event.new_value == "Renamed"


def test_timeline_has_no_write_route(client, manager, item):
    """Goal 9. The absence of the route is the enforcement."""
    client.force_authenticate(manager)
    for method in (client.put, client.patch, client.delete):
        response = method(f"/api/items/{item.id}/timeline/")
        assert response.status_code in (403, 405)


def test_staff_can_add_a_note(client, staff_wh, item):
    """Goal 9 puts notes in the timeline and does not restrict them."""
    client.force_authenticate(staff_wh)
    response = client.post(f"/api/items/{item.id}/notes/",
                           {"body": "Box damaged"}, format="json")
    assert response.status_code == 201
    assert item.timeline.get().event_type == "NOTE"


# --- Archive / restore ----------------------------------------------------

def test_archive_blocks_new_movements(client, manager, item, warehouse):
    client.force_authenticate(manager)
    client.post(f"/api/items/{item.id}/archive/")
    response = client.post("/api/movements/receipt/", {
        "item": item.id, "location": warehouse.id, "quantity": 5,
    }, format="json")
    assert response.status_code == 409


def test_restore_allows_movements_again(client, manager, item, warehouse):
    client.force_authenticate(manager)
    client.post(f"/api/items/{item.id}/archive/")
    client.post(f"/api/items/{item.id}/restore/")
    response = client.post("/api/movements/receipt/", {
        "item": item.id, "location": warehouse.id, "quantity": 5,
    }, format="json")
    assert response.status_code == 201


# --- on_hand comes from SQL -----------------------------------------------

def test_item_list_includes_on_hand(client, manager, item, warehouse):
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=42)
    client.force_authenticate(manager)
    row = client.get("/api/items/").data["results"][0]
    assert row["on_hand"] == 42


def test_item_with_no_movements_appears_with_zero(client, manager, item):
    """L-16. A LEFT JOIN + SUM without Coalesce silently drops these."""
    client.force_authenticate(manager)
    results = client.get("/api/items/").data["results"]
    assert len(results) == 1
    assert results[0]["on_hand"] == 0