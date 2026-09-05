"""Account administration: who can create a login, and how one is revoked.

There is no sign-up route to test, which is the point -- the first test here
asserts its absence, because "we never built it" and "we deliberately did not
build it" look identical in a codebase and only one of them stays true.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def client():
    return APIClient()


NEW = {
    "email": "newperson@test.local",
    "full_name": "New Person",
    "role": "STAFF",
    "password": "correct-horse-battery",
}


# --- there is no self-service registration --------------------------------

def test_account_creation_is_closed_to_anonymous_callers(client, db):
    """The whole justification for having no sign-up page: an account is read
    access to every stock position the business holds."""
    response = client.post("/api/accounts/", NEW, format="json")
    assert response.status_code in (401, 403)
    assert not User.objects.filter(email=NEW["email"]).exists()


def test_staff_cannot_create_accounts(client, staff_wh):
    """Otherwise any staff member could mint themselves a manager."""
    client.force_authenticate(staff_wh)
    response = client.post("/api/accounts/", NEW, format="json")
    assert response.status_code == 403
    assert not User.objects.filter(email=NEW["email"]).exists()


def test_staff_cannot_even_list_accounts(client, staff_wh):
    client.force_authenticate(staff_wh)
    assert client.get("/api/accounts/").status_code == 403


# --- a manager can ---------------------------------------------------------

def test_manager_creates_a_working_account(client, manager):
    """Created, and actually able to sign in -- objects.create() would store
    the password unhashed and this second half would fail."""
    client.force_authenticate(manager)
    response = client.post("/api/accounts/", NEW, format="json")
    assert response.status_code == 201

    fresh = APIClient()
    login = fresh.post(
        "/api/auth/login/",
        {"email": NEW["email"], "password": NEW["password"]},
        format="json",
    )
    assert login.status_code == 200
    assert login.data["role"] == "STAFF"


def test_the_password_is_never_echoed_back(client, manager):
    client.force_authenticate(manager)
    response = client.post("/api/accounts/", NEW, format="json")
    assert "password" not in response.data


def test_a_manager_can_create_another_manager(client, manager):
    client.force_authenticate(manager)
    response = client.post(
        "/api/accounts/", {**NEW, "role": "MANAGER"}, format="json"
    )
    assert response.status_code == 201
    assert User.objects.get(email=NEW["email"]).is_manager


def test_the_list_includes_managers(client, manager, staff_wh):
    """Unlike /api/staff/, which excludes them on purpose. You cannot audit
    who holds manager access from a list that hides the managers."""
    client.force_authenticate(manager)
    roles = {row["role"] for row in client.get("/api/accounts/").data["results"]}
    assert roles == {"MANAGER", "STAFF"}


# --- validation ------------------------------------------------------------

def test_a_duplicate_email_is_rejected_whatever_its_capitalisation(
    client, manager
):
    """Uniqueness is a functional index on Lower(email), which DRF cannot see.
    Without an explicit check this is an IntegrityError 500."""
    client.force_authenticate(manager)
    response = client.post(
        "/api/accounts/", {**NEW, "email": manager.email.upper()}, format="json"
    )
    assert response.status_code == 400
    assert "already exists" in str(response.data["email"])


def test_a_weak_password_is_refused_with_a_usable_reason(client, manager):
    """Django's own validators, so the message names the actual problem
    rather than a length rule invented at this layer."""
    client.force_authenticate(manager)
    response = client.post("/api/accounts/", {**NEW, "password": "1234"},
                           format="json")
    assert response.status_code == 400
    assert not User.objects.filter(email=NEW["email"]).exists()


# --- revoking access -------------------------------------------------------

def test_deactivating_blocks_sign_in(client, manager, staff_wh):
    staff_wh.set_password("correct-horse-battery")
    staff_wh.save()

    client.force_authenticate(manager)
    assert client.post(f"/api/accounts/{staff_wh.id}/deactivate/").status_code == 200

    fresh = APIClient()
    login = fresh.post(
        "/api/auth/login/",
        {"email": staff_wh.email, "password": "correct-horse-battery"},
        format="json",
    )
    assert login.status_code == 400


def test_deactivating_keeps_the_movements_they_recorded(
    client, manager, staff_wh, item, warehouse
):
    """The reason there is no delete route. A ledger entry whose author has
    been erased is worse than no ledger at all."""
    from apps.stock.services import stock_service as ss

    ss.record_receipt(actor=staff_wh, item=item, location=warehouse, quantity=5)

    client.force_authenticate(manager)
    client.post(f"/api/accounts/{staff_wh.id}/deactivate/")

    movements = client.get(f"/api/items/{item.id}/movements/").json()["results"]
    assert movements[0]["recorded_by_name"] == staff_wh.full_name
    assert ss.on_hand(item) == 5


def test_reactivating_restores_access(client, manager, staff_wh):
    staff_wh.set_password("correct-horse-battery")
    staff_wh.save()

    client.force_authenticate(manager)
    client.post(f"/api/accounts/{staff_wh.id}/deactivate/")
    client.post(f"/api/accounts/{staff_wh.id}/reactivate/")

    fresh = APIClient()
    login = fresh.post(
        "/api/auth/login/",
        {"email": staff_wh.email, "password": "correct-horse-battery"},
        format="json",
    )
    assert login.status_code == 200


def test_a_manager_cannot_deactivate_themselves(client, manager):
    """The lockout case. With one manager and no guard, one click leaves the
    system with nobody who can create an account -- including the account
    needed to undo it."""
    client.force_authenticate(manager)
    response = client.post(f"/api/accounts/{manager.id}/deactivate/")
    assert response.status_code == 400

    manager.refresh_from_db()
    assert manager.is_active


def test_there_is_no_delete_route(client, manager, staff_wh):
    """404 rather than 405, because the viewset declares no detail methods at
    all, so the router never generates the bare detail URL. Either code is a
    refusal; what matters is that no request deletes an account."""
    client.force_authenticate(manager)
    assert client.delete(f"/api/accounts/{staff_wh.id}/").status_code in (404, 405)
