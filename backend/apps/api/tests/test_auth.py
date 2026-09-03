"""Tests A-01 to A-07: the auth contract.

Goal 1 says the role difference must be enforced on the server, "not just
hidden in the interface". That sentence is a test specification -- these hit
the URLs directly, with no UI involved.
"""

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def client():
    return APIClient()


# --- A-01, A-06 -----------------------------------------------------------

def test_anonymous_gets_401_not_302(client):
    """An SPA cannot follow a redirect to a login page. It needs a status
    code it can branch on."""
    response = client.get("/api/auth/me/")
    assert response.status_code == 401


def test_healthz_is_public(client, db):
    """Needs the db fixture: healthz deliberately touches the database, since
    a process that is up but cannot reach Postgres is not healthy in any
    useful sense."""
    assert client.get("/healthz/").status_code == 200


def test_healthz_reports_unhealthy_when_database_is_unreachable(client, monkeypatch):
    """No db fixture, so database access is blocked. The check should report
    the failure rather than raise."""
    response = client.get("/healthz/")
    assert response.status_code == 503
    assert response.json()["status"] == "error"


# --- login ---------------------------------------------------------------

def test_login_returns_user_and_sets_session(client, manager):
    manager.set_password("secret123")
    manager.save()

    response = client.post(
        "/api/auth/login/",
        {"email": manager.email, "password": "secret123"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["role"] == "MANAGER"
    assert response.data["is_manager"] is True

    # The session now carries the request.
    assert client.get("/api/auth/me/").status_code == 200


def test_login_is_case_insensitive_on_email(client, manager):
    """The Lower() constraint means Manager@... and manager@... are the same
    account, so login has to accept either."""
    manager.set_password("secret123")
    manager.save()

    response = client.post(
        "/api/auth/login/",
        {"email": manager.email.upper(), "password": "secret123"},
        format="json",
    )
    assert response.status_code == 200


def test_wrong_password_rejected(client, manager):
    manager.set_password("secret123")
    manager.save()
    response = client.post(
        "/api/auth/login/",
        {"email": manager.email, "password": "wrong"},
        format="json",
    )
    assert response.status_code == 400


def test_unknown_email_gives_same_error_as_wrong_password(client, manager):
    """Distinguishing them would tell an attacker which addresses exist."""
    manager.set_password("secret123")
    manager.save()

    unknown = client.post(
        "/api/auth/login/",
        {"email": "nobody@test.local", "password": "secret123"},
        format="json",
    )
    wrong_password = client.post(
        "/api/auth/login/",
        {"email": manager.email, "password": "wrong"},
        format="json",
    )
    assert unknown.status_code == wrong_password.status_code
    assert unknown.data["detail"] == wrong_password.data["detail"]


# --- A-05 ----------------------------------------------------------------

def test_logout_ends_the_session(client, manager):
    manager.set_password("secret123")
    manager.save()
    client.post(
        "/api/auth/login/",
        {"email": manager.email, "password": "secret123"},
        format="json",
    )
    assert client.post("/api/auth/logout/").status_code == 200
    assert client.get("/api/auth/me/").status_code == 401


# --- location scoping in /me ---------------------------------------------

def test_manager_sees_every_active_location(client, manager, warehouse, shop):
    client.force_authenticate(manager)
    codes = {loc["code"] for loc in client.get("/api/auth/me/").data["locations"]}
    assert codes == {"WH", "SF"}


def test_staff_sees_only_assigned_locations(client, staff_wh, warehouse, shop):
    """staff_wh is assigned to the warehouse only. The shop must not appear,
    because this list drives the movement form dropdowns."""
    client.force_authenticate(staff_wh)
    codes = {loc["code"] for loc in client.get("/api/auth/me/").data["locations"]}
    assert codes == {"WH"}

def test_csrf_endpoint_returns_the_token_in_the_body(client):
    """Not only as a cookie.

    In production the SPA is served from a different domain than this API, so
    document.cookie on the frontend origin cannot read a cookie set for the
    API's domain. The browser still sends it, but the client has no way to
    echo it in the X-CSRFToken header unless we hand it over in the body.
    Reading it from the cookie works only when both sides share a hostname,
    which is true in development and false in production.
    """
    response = client.get("/api/auth/csrf/")
    assert response.status_code == 200

    token = response.json()["csrftoken"]
    # Django rejects a token that is neither a 32-char secret nor a 64-char
    # masked token with "has incorrect length" -- which is exactly the error
    # an empty header produced before this endpoint returned anything.
    assert len(token) in (32, 64)


def test_login_succeeds_using_only_the_token_from_the_body(client, manager):
    """The end-to-end version of the above: sign in without ever reading
    document.cookie, the way the deployed frontend has to."""
    token = client.get("/api/auth/csrf/").json()["csrftoken"]
    response = client.post(
        "/api/auth/login/",
        data={"email": "manager@test.local", "password": "x"},
        content_type="application/json",
        headers={"x-csrftoken": token},
    )
    assert response.status_code == 200, response.content
