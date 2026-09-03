"""The alerts endpoints.

Goal 1 says the role rule is enforced on the server, so the permission tests
here hit the endpoint directly rather than trusting that the UI hides a button.
"""

import pytest

from apps.catalog.models import Item
from apps.stock.services import stock_service as ss


@pytest.fixture
def low_item(db, manager, warehouse, category):
    item = Item.objects.create(
        sku="LOW-1", name="Low stock item", reorder_level=10, category=category
    )
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=5, note="")
    return item


def test_alerts_require_authentication(client, low_item):
    assert client.get("/api/alerts/").status_code == 401
    assert client.get("/api/alerts/count/").status_code == 401


def test_staff_may_read_alerts(client, staff_wh, low_item):
    """Staff need to know what is running out to do anything about it."""
    client.force_login(staff_wh)
    response = client.get("/api/alerts/")
    assert response.status_code == 200
    assert [row["sku"] for row in response.json()["results"]] == ["LOW-1"]


def test_staff_may_not_dismiss(client, staff_wh, low_item):
    """A dismissal hides information from everyone else, so it is a
    manager's call -- and the server is what says so."""
    client.force_login(staff_wh)
    response = client.post(f"/api/alerts/{low_item.id}/dismiss/")
    assert response.status_code == 403


def test_manager_dismisses_and_the_alert_disappears(client, manager, low_item):
    client.force_login(manager)

    dismissed = client.post(f"/api/alerts/{low_item.id}/dismiss/")
    assert dismissed.status_code == 200
    # The item comes back so the client can update without a refetch, and it
    # carries on_hand, which only the annotated queryset provides.
    assert dismissed.json()["sku"] == "LOW-1"
    assert dismissed.json()["on_hand"] == 5

    assert client.get("/api/alerts/").json()["count"] == 0
    assert client.get("/api/alerts/count/").json()["count"] == 0


def test_count_endpoint_agrees_with_the_list(client, manager, low_item, category):
    Item.objects.create(
        sku="LOW-2", name="Another", reorder_level=5, category=category
    )
    client.force_login(manager)
    assert client.get("/api/alerts/count/").json()["count"] == 2
    assert client.get("/api/alerts/").json()["count"] == 2


def test_dismissing_an_unknown_item_is_404(client, manager):
    client.force_login(manager)
    assert client.post("/api/alerts/999999/dismiss/").status_code == 404


def test_alert_returns_through_the_api_after_a_recovery_cycle(
    client, manager, warehouse, low_item
):
    """The same cycle as the service test, driven the way the app drives it."""
    client.force_login(manager)
    client.post(f"/api/alerts/{low_item.id}/dismiss/")
    assert client.get("/api/alerts/count/").json()["count"] == 0

    ss.record_receipt(
        actor=manager, item=low_item, location=warehouse, quantity=20, note=""
    )
    ss.record_issue(
        actor=manager, item=low_item, location=warehouse, quantity=17, note=""
    )

    assert client.get("/api/alerts/count/").json()["count"] == 1
