"""The item list filter layer.

These test apply_filters directly rather than through the HTTP endpoint. The
interesting risks live in the SQL -- an annotation that drops rows, a location
filter that double-counts a join -- and going through the view would only add
noise between the assertion and the thing being asserted.

The pagination tests at the bottom are the exception: the envelope DRF wraps
around the queryset is the thing under test there, so they go over HTTP.
"""
import pytest
from rest_framework.test import APIClient

from apps.api.filters import apply_filters
from apps.catalog.models import Item
from apps.stock.services import stock_service as ss


@pytest.fixture
def stocked(db, manager, warehouse, shop, category):
    a = Item.objects.create(sku="A-1", name="Alpha bolt", reorder_level=10, category=category)
    b = Item.objects.create(sku="B-2", name="Beta washer", reorder_level=5, category=category)
    ss.record_receipt(actor=manager, item=a, location=warehouse, quantity=30, note="")
    ss.record_receipt(actor=manager, item=a, location=shop, quantity=7, note="")
    ss.record_receipt(actor=manager, item=b, location=warehouse, quantity=2, note="")
    return a, b


@pytest.fixture
def client():
    return APIClient()


def q(**params):
    return apply_filters(Item.objects.all(), params)


def test_on_hand_is_global_without_location(stocked):
    a, b = stocked
    got = {i.sku: i.on_hand for i in q()}
    assert got == {"A-1": 37, "B-2": 2}, got


def test_on_hand_is_scoped_when_location_given(stocked, warehouse, shop):
    a, b = stocked
    wh = {i.sku: i.on_hand for i in q(location=str(warehouse.id))}
    sf = {i.sku: i.on_hand for i in q(location=str(shop.id))}
    assert wh == {"A-1": 30, "B-2": 2}, wh
    # Only A moved at the shop, so B must not appear at all.
    assert sf == {"A-1": 7}, sf


def test_item_with_no_movements_still_appears(db, category):
    Item.objects.create(sku="Z-9", name="Never moved", reorder_level=1, category=category)
    got = {i.sku: i.on_hand for i in q()}
    assert got["Z-9"] == 0


def test_search_matches_name_and_sku(stocked):
    assert [i.sku for i in q(q="alpha")] == ["A-1"]
    assert [i.sku for i in q(q="b-2")] == ["B-2"]
    assert [i.sku for i in q(q="zzz")] == []


def test_below_reorder_uses_lte(stocked):
    # B: on_hand 2 <= reorder 5 -> included. A: 37 > 10 -> excluded.
    assert [i.sku for i in q(below_reorder="1")] == ["B-2"]


def test_archived_hidden_by_default(stocked):
    a, _ = stocked
    a.is_archived = True
    a.save(update_fields=["is_archived"])
    assert [i.sku for i in q()] == ["B-2"]
    assert [i.sku for i in q(archived="1")] == ["A-1"]
    assert sorted(i.sku for i in q(archived="all")) == ["A-1", "B-2"]


def test_bad_sort_falls_back_to_default(stocked):
    assert [i.sku for i in q(sort="; DROP TABLE catalog_item")] == ["A-1", "B-2"]


def test_unknown_location_returns_nothing(stocked):
    """Not the unfiltered list. A stale location id in a bookmarked URL must
    not quietly produce global quantities labelled as one location's."""
    assert list(q(location="999999")) == []


def test_junk_ids_return_nothing_rather_than_500(stocked):
    """A pk lookup on a raw query string raises ValueError, not DoesNotExist,
    so this has to be coerced before it reaches the ORM."""
    assert list(q(location="not-an-id")) == []
    assert list(q(category="not-an-id")) == []


def test_unknown_category_returns_nothing(stocked):
    assert list(q(category="999999")) == []


def test_location_and_below_reorder_compare_a_shelf_to_a_global_level(stocked, shop):
    """The one genuinely ambiguous combination in goal 6, pinned deliberately.

    A reorder level belongs to the item, not to a location -- there is no
    "reorder level at the warehouse". So when both filters are on, this
    compares that location's quantity against the item's global level, and
    answers "which items are running low *here*".

    Item A holds 7 at the shop against a level of 10, so it qualifies even
    though its global 37 is far above the level. The alternative reading --
    global stock at-or-below the level, listed for one location -- would
    exclude it, and would make the answer independent of the location filter,
    which is a strange thing for a location filter to be.
    """
    assert [i.sku for i in q(location=str(shop.id), below_reorder="1")] == ["A-1"]

    # And the global view disagrees with it, which is the whole point.
    assert [i.sku for i in q(below_reorder="1")] == ["B-2"]


# --- pagination -----------------------------------------------------------
#
# These go through the API rather than the queryset, because the thing under
# test is the envelope DRF wraps around it, not the filtering.

def test_pagination_reports_the_total_not_the_page_size(client, manager, category):
    """Goal 6 asks for "pagination showing the total number of matches".

    PAGE_SIZE is 25, so 30 items make the distinction visible: count must be
    30 while results holds 25. A count taken from len(results) would look
    correct on every list short enough to fit one page, which is exactly why
    this needs more items than that.
    """
    Item.objects.bulk_create([
        Item(sku=f"P-{n:03d}", name=f"Paginated {n:03d}",
             reorder_level=1, category=category)
        for n in range(30)
    ])
    client.force_authenticate(manager)

    first = client.get("/api/items/").json()
    assert first["count"] == 30
    assert len(first["results"]) == 25
    assert first["next"] is not None

    second = client.get("/api/items/?page=2").json()
    assert second["count"] == 30
    assert len(second["results"]) == 5

    # No row appears on both pages. The id tiebreaker in the sort is what
    # guarantees this; without it two equal names can swap places between the
    # two queries and one item is served twice while another is never seen.
    assert not ({r["sku"] for r in first["results"]}
                & {r["sku"] for r in second["results"]})


def test_the_total_counts_matches_not_every_item(client, manager, category):
    """The count has to be taken after filtering. Reporting the table size
    would tell someone searching for one item that there are thirty."""
    Item.objects.bulk_create([
        Item(sku=f"P-{n:03d}", name=f"Paginated {n:03d}",
             reorder_level=1, category=category)
        for n in range(30)
    ])
    client.force_authenticate(manager)

    assert client.get("/api/items/?q=Paginated 007").json()["count"] == 1


def test_a_page_past_the_end_is_404_not_an_empty_list(client, manager, item):
    """DRF's own behaviour, pinned deliberately: an empty page and "you asked
    for a page that does not exist" are different answers, and the frontend
    branches on the difference rather than rendering an empty table."""
    client.force_authenticate(manager)
    assert client.get("/api/items/?page=99").status_code == 404
