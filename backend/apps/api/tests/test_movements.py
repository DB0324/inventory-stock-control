"""The movement endpoints. Status codes are the contract."""

import pytest
from rest_framework.test import APIClient

from apps.stock.models import LedgerEntry, StockMovement


@pytest.fixture
def client():
    return APIClient()


def test_receipt_returns_updated_balance(client, manager, item, warehouse):
    client.force_authenticate(manager)
    response = client.post("/api/movements/receipt/", {
        "item": item.id, "location": warehouse.id, "quantity": 50,
    }, format="json")
    assert response.status_code == 201
    assert response.data["on_hand"]["WH"] == 50
    assert response.data["on_hand_total"] == 50


def test_transfer_moves_without_creating(client, manager, item, warehouse, shop):
    client.force_authenticate(manager)
    client.post("/api/movements/receipt/", {
        "item": item.id, "location": warehouse.id, "quantity": 50,
    }, format="json")
    response = client.post("/api/movements/transfer/", {
        "item": item.id, "source": warehouse.id,
        "destination": shop.id, "quantity": 20,
    }, format="json")
    assert response.status_code == 201
    assert response.data["on_hand"] == {"WH": 30, "SF": 20}
    assert response.data["on_hand_total"] == 50


def test_overdraw_returns_409_not_400(client, manager, item, warehouse, shop):
    """A-16. The request was well formed; it conflicts with current state.
    400 would tell the client to fix its input, which is wrong advice."""
    client.force_authenticate(manager)
    client.post("/api/movements/receipt/", {
        "item": item.id, "location": warehouse.id, "quantity": 10,
    }, format="json")
    before = StockMovement.objects.count()

    response = client.post("/api/movements/transfer/", {
        "item": item.id, "source": warehouse.id,
        "destination": shop.id, "quantity": 20,
    }, format="json")

    assert response.status_code == 409
    assert "holds 10" in response.data["detail"]
    assert StockMovement.objects.count() == before


def test_adjustment_without_reason_is_400(client, manager, item, warehouse):
    client.force_authenticate(manager)
    response = client.post("/api/movements/adjustment/", {
        "item": item.id, "location": warehouse.id, "quantity": 5,
    }, format="json")
    assert response.status_code == 400


def test_staff_cannot_post_adjustment(client, staff_wh, item, warehouse):
    """A-09. Goal 1 lists adjustments as manager-only."""
    client.force_authenticate(staff_wh)
    response = client.post("/api/movements/adjustment/", {
        "item": item.id, "location": warehouse.id,
        "quantity": 5, "reason": "miscount",
    }, format="json")
    assert response.status_code == 403


def test_staff_refused_at_unassigned_location(client, staff_wh, item, shop):
    """A-12. staff_wh is assigned to the warehouse only."""
    client.force_authenticate(staff_wh)
    response = client.post("/api/movements/receipt/", {
        "item": item.id, "location": shop.id, "quantity": 5,
    }, format="json")
    assert response.status_code == 403
    assert LedgerEntry.objects.count() == 0


def test_staff_transfer_checks_both_ends(client, manager, staff_wh,
                                         item, warehouse, shop):
    """A-14. Source assigned, destination not. Must still refuse."""
    from apps.stock.services import stock_service as ss
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=50)

    client.force_authenticate(staff_wh)
    response = client.post("/api/movements/transfer/", {
        "item": item.id, "source": warehouse.id,
        "destination": shop.id, "quantity": 10,
    }, format="json")
    assert response.status_code == 403


def test_self_transfer_is_400(client, manager, item, warehouse):
    client.force_authenticate(manager)
    response = client.post("/api/movements/transfer/", {
        "item": item.id, "source": warehouse.id,
        "destination": warehouse.id, "quantity": 5,
    }, format="json")
    assert response.status_code == 400


def test_movements_have_no_mutation_route(client, manager, item, warehouse):
    """A-17. There is no URL to change a recorded movement."""
    client.force_authenticate(manager)
    response = client.post("/api/movements/receipt/", {
        "item": item.id, "location": warehouse.id, "quantity": 5,
    }, format="json")
    movement_id = response.data["movement"]["id"]

    for path in (f"/api/movements/{movement_id}/",
                 f"/api/movements/receipt/{movement_id}/"):
        assert client.delete(path).status_code in (403, 404, 405)