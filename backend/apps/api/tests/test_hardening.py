"""Production hardening: rate limiting, session behaviour, response headers.

None of this is in the ten goals. All of it is the difference between a demo
and something that could be pointed at the internet.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def client():
    return APIClient()


def attempt(client, email, password="wrong"):
    return client.post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    )


# --- rate limiting --------------------------------------------------------

def test_repeated_failures_against_one_account_are_throttled(client, manager):
    """Five a minute against one email. The sixth is refused before the
    password is even checked, which is what makes a password list useless."""
    for _ in range(5):
        assert attempt(client, manager.email).status_code == 400

    blocked = attempt(client, manager.email)
    assert blocked.status_code == 429


def test_the_throttle_response_says_when_to_retry(client, manager):
    for _ in range(5):
        attempt(client, manager.email)
    blocked = attempt(client, manager.email)
    assert blocked.status_code == 429
    # Without Retry-After a client can only guess, and guessing means
    # hammering.
    assert "Retry-After" in blocked


def test_the_email_limit_is_case_insensitive(client, manager):
    """MANAGER@... and manager@... are the same account -- the model's
    uniqueness is on Lower(email) -- so they must share one budget. Keyed on
    the raw string, an attacker gets a fresh five attempts per capitalisation
    and the limit means nothing."""
    variants = [
        manager.email,
        manager.email.upper(),
        manager.email.capitalize(),
        manager.email.title(),
        manager.email.swapcase(),
    ]
    for email in variants:
        attempt(client, email)

    assert attempt(client, manager.email.upper()).status_code == 429


def test_a_different_account_is_not_blocked_by_another_s_failures(
    client, manager, staff_wh
):
    """The per-email limit must not become a way to lock someone else out.
    Only the per-IP limit applies across accounts, and it is set higher."""
    for _ in range(5):
        attempt(client, manager.email)
    assert attempt(client, manager.email).status_code == 429

    assert attempt(client, staff_wh.email).status_code == 400


def test_a_correct_password_still_works_below_the_limit(client, manager):
    manager.set_password("correct-horse-battery")
    manager.save()

    for _ in range(3):
        attempt(client, manager.email)

    ok = attempt(client, manager.email, password="correct-horse-battery")
    assert ok.status_code == 200


def test_a_malformed_request_does_not_consume_someone_else_s_budget(
    client, manager
):
    """Requests with no email key on nothing, so they must not fall into a
    single shared bucket that a real user's attempts also land in."""
    for _ in range(8):
        client.post("/api/auth/login/", {"password": "x"}, format="json")

    manager.set_password("correct-horse-battery")
    manager.save()
    assert attempt(client, manager.email, "correct-horse-battery").status_code == 200


# --- sessions and roles ---------------------------------------------------

def test_signing_in_rotates_the_session_key(client, manager):
    """Session fixation. If the key survived login, anyone who could set a
    cookie before sign-in would hold a valid session afterwards."""
    manager.set_password("correct-horse-battery")
    manager.save()

    client.get("/api/auth/csrf/")
    before = client.cookies.get("sessionid")
    before = before.value if before else None

    attempt(client, manager.email, "correct-horse-battery")
    after = client.cookies["sessionid"].value

    assert after != before


def test_deactivating_ends_a_session_already_in_progress(client, manager, staff_wh):
    """Revoking access has to reach the people already signed in. Blocking
    only future logins would leave a dismissed employee working until their
    cookie happened to expire."""
    staff_wh.set_password("correct-horse-battery")
    staff_wh.save()
    attempt(client, staff_wh.email, "correct-horse-battery")
    assert client.get("/api/auth/me/").status_code == 200

    staff_wh.is_active = False
    staff_wh.save(update_fields=["is_active"])

    assert client.get("/api/auth/me/").status_code == 401


def test_a_role_change_applies_to_the_session_already_in_progress(
    client, staff_wh, category
):
    """Role is read from the database on every request rather than copied
    into the session at login. Promotion and demotion therefore take effect
    on the next request, not the next sign-in."""
    staff_wh.set_password("correct-horse-battery")
    staff_wh.save()
    attempt(client, staff_wh.email, "correct-horse-battery")

    payload = {"sku": "R-1", "name": "Role test", "unit_of_measure": "EA",
               "reorder_level": 1, "category": category.id}
    assert client.post("/api/items/", payload, format="json").status_code == 403

    staff_wh.role = User.Role.MANAGER
    staff_wh.save(update_fields=["role"])

    assert client.post("/api/items/", payload, format="json").status_code == 201


def test_demotion_applies_immediately_too(client, manager, category):
    """The direction that actually matters for security."""
    manager.set_password("correct-horse-battery")
    manager.save()
    attempt(client, manager.email, "correct-horse-battery")

    manager.role = User.Role.STAFF
    manager.save(update_fields=["role"])

    response = client.post("/api/items/", {
        "sku": "R-2", "name": "Demoted", "unit_of_measure": "EA",
        "reorder_level": 1, "category": category.id,
    }, format="json")
    assert response.status_code == 403


def test_changing_a_password_ends_other_sessions(client, manager):
    """Django keeps a hash of the password in the session and checks it on
    every request. The point is that "someone knows my password" is fixed by
    changing it -- which only works if the sessions they opened die too."""
    manager.set_password("correct-horse-battery")
    manager.save()
    attempt(client, manager.email, "correct-horse-battery")
    assert client.get("/api/auth/me/").status_code == 200

    manager.set_password("a-different-one-entirely")
    manager.save()

    assert client.get("/api/auth/me/").status_code == 401


def test_logout_makes_the_cookie_useless_not_just_absent(client, manager):
    """The session is destroyed server-side, so replaying the old cookie
    fails. If logout only cleared the browser's copy, a captured cookie would
    keep working."""
    manager.set_password("correct-horse-battery")
    manager.save()
    attempt(client, manager.email, "correct-horse-battery")
    stolen = client.cookies["sessionid"].value

    client.post("/api/auth/logout/")

    replay = APIClient()
    replay.cookies["sessionid"] = stolen
    assert replay.get("/api/auth/me/").status_code == 401


# --- response headers -----------------------------------------------------

def test_api_responses_are_not_stored_by_caches(client, manager, item):
    """Sign out, press Back, and a cached response would render the previous
    user's stock positions without ever reaching the server."""
    client.force_authenticate(manager)
    response = client.get("/api/items/")
    assert "no-store" in response["Cache-Control"]
    assert "Cookie" in response["Vary"]


def test_the_health_check_is_still_cacheable(client, db):
    """The blanket rule is scoped to /api/. A liveness probe is not user
    data and load balancers hit it constantly."""
    response = client.get("/healthz/")
    assert response.get("Cache-Control") is None


# --- information disclosure -----------------------------------------------

def test_an_unhealthy_health_check_reveals_nothing(client, monkeypatch):
    """psycopg names the host, port, user and database in its connection
    errors, and this endpoint is public. The detail belongs in the log."""
    response = client.get("/healthz/")
    assert response.status_code == 503

    body = response.json()
    assert body == {"status": "error"}

    text = response.content.decode().lower()
    for leak in ("password", "neon", "postgres", "5432", "user", "host"):
        assert leak not in text
