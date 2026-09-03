"""The item list filter layer.

These test apply_filters directly rather than through the HTTP endpoint. The
interesting risks live in the SQL -- an annotation that drops rows, a location
filter that double-counts a join -- and going through the view would only add
noise between the assertion and the thing being asserted.
"""
import pytest

from apps.api.filters import apply_filters
from apps.catalog.models import Category, Item
from apps.stock.services import stock_service as ss


@pytest.fixture
def stocked(db, manager, warehouse, shop, category):
    a = Item.objects.create(sku="A-1", name="Alpha bolt", reorder_level=10, category=category)
    b = Item.objects.create(sku="B-2", name="Beta washer", reorder_level=5, category=category)
    ss.record_receipt(actor=manager, item=a, location=warehouse, quantity=30, note="")
    ss.record_receipt(actor=manager, item=a, location=shop, quantity=7, note="")
    ss.record_receipt(actor=manager, item=b, location=warehouse, quantity=2, note="")
    return a, b


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
