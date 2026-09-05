"""Two people editing the same item.

The ledger's concurrency story is covered by apps/stock/tests/test_concurrency.py
with real threads -- that is about quantities, and it is airtight. This file is
about the other half of the question: the item's own fields, where the risk is
not a wrong balance but a silently discarded edit.
"""

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Item


@pytest.fixture
def client():
    return APIClient()


def test_a_new_item_starts_at_version_one(client, manager, category):
    client.force_authenticate(manager)
    response = client.post("/api/items/", {
        "sku": "V-1", "name": "Versioned", "unit_of_measure": "EA",
        "reorder_level": 5, "category": category.id,
    }, format="json")
    assert response.data["version"] == 1


def test_each_edit_increments_the_version(client, manager, item):
    client.force_authenticate(manager)
    first = client.patch(f"/api/items/{item.id}/", {"name": "One"},
                         format="json")
    assert first.data["version"] == 2

    second = client.patch(f"/api/items/{item.id}/", {"name": "Two"},
                          format="json")
    assert second.data["version"] == 3


def test_a_stale_edit_is_refused(client, manager, item):
    """The scenario in full.

    Two managers open the same item, both holding version 1. The first saves
    and the item becomes version 2. The second then saves against version 1 --
    the copy they were actually looking at -- and must be told, rather than
    quietly overwriting a change they never saw.
    """
    client.force_authenticate(manager)

    client.patch(f"/api/items/{item.id}/",
                 {"name": "Saved first", "expected_version": 1}, format="json")

    late = client.patch(f"/api/items/{item.id}/",
                        {"reorder_level": 99, "expected_version": 1},
                        format="json")

    assert late.status_code == 409
    assert late.data["code"] == "edit_conflict"

    item.refresh_from_db()
    assert item.name == "Saved first"
    assert item.reorder_level == 10   # the fixture's value, untouched


def test_the_retry_succeeds_once_the_client_has_the_current_version(
    client, manager, item
):
    """A 409 has to be recoverable, or it is just a wall. Reload, and the same
    edit goes through."""
    client.force_authenticate(manager)
    client.patch(f"/api/items/{item.id}/",
                 {"name": "Saved first", "expected_version": 1}, format="json")

    current = client.get(f"/api/items/{item.id}/").data["version"]
    retry = client.patch(f"/api/items/{item.id}/",
                         {"reorder_level": 99, "expected_version": current},
                         format="json")
    assert retry.status_code == 200
    assert retry.data["reorder_level"] == 99


def test_omitting_the_version_keeps_last_write_wins(client, manager, item):
    """Backwards compatible on purpose. A bulk load is deliberately the
    authority over whatever is in the database, so it does not opt in."""
    client.force_authenticate(manager)
    client.patch(f"/api/items/{item.id}/", {"name": "First"}, format="json")
    response = client.patch(f"/api/items/{item.id}/", {"name": "Second"},
                            format="json")
    assert response.status_code == 200
    assert Item.objects.get(pk=item.id).name == "Second"


def test_a_refused_edit_leaves_no_timeline_event(client, manager, item):
    """The conflict is raised before record_changes runs, and the whole method
    is one transaction -- so a rejected edit leaves no trace claiming it
    happened. A timeline with phantom entries would undermine goal 9."""
    client.force_authenticate(manager)
    client.patch(f"/api/items/{item.id}/",
                 {"name": "Winner", "expected_version": 1}, format="json")

    before = item.timeline.count()
    client.patch(f"/api/items/{item.id}/",
                 {"name": "Loser", "expected_version": 1}, format="json")
    assert item.timeline.count() == before


def test_version_is_not_settable_by_the_client(client, manager, item):
    """It is read-only in the serializer. A client that could write it could
    make its own stale edit look current."""
    client.force_authenticate(manager)
    response = client.patch(f"/api/items/{item.id}/",
                            {"name": "Renamed", "version": 500}, format="json")
    assert response.status_code == 200
    assert response.data["version"] == 2
