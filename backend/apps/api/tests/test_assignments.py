"""Location assignment endpoints (goal 5).

The rule these enforce is that staff may only record movements where they are
assigned. That rule lives in the service layer and is tested there; what
matters here is that only a manager can change who is assigned, and that the
audit trail cannot be forged.
"""

import pytest

from apps.stock.models import LocationAssignment


def test_staff_list_requires_a_manager(client, staff_wh):
    client.force_login(staff_wh)
    assert client.get("/api/staff/").status_code == 403
    assert client.get("/api/assignments/").status_code == 403


def test_manager_sees_staff_with_their_assignments(client, manager, staff_wh, warehouse):
    client.force_login(manager)
    response = client.get("/api/staff/")
    assert response.status_code == 200

    rows = response.json()["results"]
    assert [row["email"] for row in rows] == ["staff@test.local"]
    assert [a["location_code"] for a in rows[0]["assignments"]] == ["WH"]


def test_managers_are_absent_from_the_staff_list(client, manager, staff_wh):
    """They hold no assignment rows -- their reach is universal by role, so
    showing checkboxes for them would imply an access model that does not
    exist."""
    client.force_login(manager)
    emails = [row["email"] for row in client.get("/api/staff/").json()["results"]]
    assert "manager@test.local" not in emails


def test_manager_grants_access(client, manager, staff_wh, shop):
    client.force_login(manager)
    response = client.post(
        "/api/assignments/",
        data={"user": staff_wh.id, "location": shop.id},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert LocationAssignment.objects.filter(user=staff_wh, location=shop).exists()


def test_the_grantor_is_the_request_user_not_the_payload(client, manager, staff_wh, shop):
    """A forgeable audit trail is worse than none, because it looks
    trustworthy. assigned_by is read-only and taken from the session."""
    client.force_login(manager)
    client.post(
        "/api/assignments/",
        data={"user": staff_wh.id, "location": shop.id, "assigned_by": staff_wh.id},
        content_type="application/json",
    )
    assignment = LocationAssignment.objects.get(user=staff_wh, location=shop)
    assert assignment.assigned_by == manager


def test_duplicate_grant_is_rejected(client, manager, staff_wh, warehouse):
    """The unique constraint is at the database, so two managers clicking at
    the same moment cannot both win."""
    client.force_login(manager)
    response = client.post(
        "/api/assignments/",
        data={"user": staff_wh.id, "location": warehouse.id},
        content_type="application/json",
    )
    assert response.status_code == 400


def test_manager_revokes_access(client, manager, staff_wh, warehouse):
    client.force_login(manager)
    assignment = LocationAssignment.objects.get(user=staff_wh, location=warehouse)
    assert client.delete(f"/api/assignments/{assignment.id}/").status_code == 204
    assert not LocationAssignment.objects.filter(pk=assignment.pk).exists()


def test_staff_cannot_grant_themselves_access(client, staff_wh, shop):
    """The obvious attack, and the reason this is not merely a hidden button."""
    client.force_login(staff_wh)
    response = client.post(
        "/api/assignments/",
        data={"user": staff_wh.id, "location": shop.id},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert not LocationAssignment.objects.filter(user=staff_wh, location=shop).exists()


@pytest.mark.django_db
def test_revoking_does_not_delete_the_movements_they_recorded(
    client, manager, staff_wh, warehouse, item
):
    """Access is about what you may do next, not a rewrite of what happened."""
    from apps.stock.services import stock_service as ss

    ss.record_receipt(actor=staff_wh, item=item, location=warehouse, quantity=5)
    assignment = LocationAssignment.objects.get(user=staff_wh, location=warehouse)

    client.force_login(manager)
    client.delete(f"/api/assignments/{assignment.id}/")

    assert item.movements.filter(recorded_by=staff_wh).count() == 1
