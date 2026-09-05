"""Query-count regressions.

These are the cheapest scalability tests there are. Nothing here measures
speed -- speed depends on the machine and would make the suite flaky. What
they pin is *shape*: a list endpoint must cost a fixed number of queries
regardless of how many rows it returns.

That distinction is the whole point. An N+1 does not look slow with the
twenty-four items the seed data creates; it looks slow at two thousand, in
production, months after the select_related that prevented it was dropped
during an unrelated refactor. A count assertion fails immediately, on the
laptop of whoever dropped it.
"""

import pytest
from rest_framework.test import APIClient

from apps.catalog.models import Item
from apps.stock.models import LocationAssignment
from apps.stock.services import stock_service as ss


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def many_items(db, manager, category, warehouse):
    """Twenty items, each with movements, so an N+1 has something to reveal."""
    items = Item.objects.bulk_create([
        Item(sku=f"Q-{n:03d}", name=f"Queried {n:03d}",
             reorder_level=5, category=category)
        for n in range(20)
    ])
    for item in items:
        ss.record_receipt(actor=manager, item=item, location=warehouse,
                          quantity=10)
    return items


def test_the_item_list_does_not_scale_with_the_number_of_items(
    client, manager, many_items, django_assert_num_queries
):
    """One page of 20 items costs the same as one page of 2.

    on_hand is a SQL annotation and the category comes from select_related, so
    neither adds a query per row. Drop either and this test fails with a count
    in the twenties rather than a vague sense that the page got slower.
    """
    client.force_authenticate(manager)

    # Warm the session and user lookups so they are not counted as part of the
    # list's own cost -- they happen once per request whatever it returns.
    client.get("/api/items/")

    with django_assert_num_queries(2):
        # One COUNT for the pagination total, one for the page itself.
        response = client.get("/api/items/")
    assert len(response.data["results"]) == 20


def test_filtering_and_sorting_do_not_add_queries(
    client, manager, many_items, category, django_assert_num_queries
):
    """Goal 6 says the filtering happens on the server. This is the proof that
    it happens in the database rather than in Python after a broad fetch --
    the query count is identical whether or not filters are applied."""
    client.force_authenticate(manager)
    client.get("/api/items/")

    with django_assert_num_queries(2):
        client.get(
            f"/api/items/?q=Queried&category={category.id}"
            "&sort=-on_hand&below_reorder=0"
        )


def test_the_staff_grid_does_not_query_per_person(
    client, manager, warehouse, shop, django_assert_num_queries
):
    """The assignments screen shows every staff member at once, so a query per
    person is the failure mode it is most exposed to. prefetch_related keeps
    it flat."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    for n in range(10):
        person = User.objects.create_user(
            email=f"person{n}@test.local", password="x",
            full_name=f"Person {n}", role=User.Role.STAFF,
        )
        LocationAssignment.objects.create(
            user=person, location=warehouse, assigned_by=manager
        )
        LocationAssignment.objects.create(
            user=person, location=shop, assigned_by=manager
        )

    client.force_authenticate(manager)
    client.get("/api/staff/")

    # Count, page, and one prefetch that joins the assignments to both their
    # location and their grantor. Ten people holding twenty assignments cost
    # the same three queries as one person holding none.
    #
    # This test earned its place immediately: the first version of the view
    # prefetched only the location, and the serializer's assigned_by_name then
    # fetched a user per assignment -- twenty-four queries for this page.
    with django_assert_num_queries(3):
        response = client.get("/api/staff/")
    assert len(response.data["results"]) == 10


def test_the_alert_count_is_a_single_aggregate(
    client, manager, many_items, django_assert_num_queries
):
    """The navigation badge renders on every page and refetches on a timer, so
    it is the most-called endpoint in the app. It must never serialize a list
    to arrive at a number."""
    client.force_authenticate(manager)
    client.get("/api/alerts/count/")

    with django_assert_num_queries(1):
        client.get("/api/alerts/count/")
