"""Dashboard aggregates (goal 8).

The date boundaries carry the risk here. "Today" and "this week" are business
questions answered in the configured business timezone, and an evening
movement in Asia/Kolkata is already tomorrow in UTC -- so a naive
implementation is wrong precisely in the evening, when someone is most likely
to be looking.
"""

from datetime import timedelta

import pytest

from apps.catalog.models import Item
from apps.stock.services import alert_service, dashboard_service as ds
from apps.stock.services import stock_service as ss
from apps.stock.services.immutability import immutability_disabled


@pytest.fixture
def stocked(db, manager, warehouse, shop, category):
    a = Item.objects.create(sku="D-1", name="Alpha", reorder_level=10, category=category)
    b = Item.objects.create(sku="D-2", name="Beta", reorder_level=100, category=category)
    ss.record_receipt(actor=manager, item=a, location=warehouse, quantity=50)
    ss.record_receipt(actor=manager, item=b, location=shop, quantity=20)
    return a, b


def test_headline_numbers(stocked, manager, warehouse):
    a, _ = stocked
    ss.record_issue(actor=manager, item=a, location=warehouse, quantity=5)

    numbers = ds.headline_numbers()
    assert numbers["active_items"] == 2
    # D-2 has 20 against a reorder level of 100.
    assert numbers["low_stock_items"] == 1
    assert numbers["movements_today"] == 3
    assert numbers["items_moved_this_week"] == 2


def test_archived_items_are_not_active(stocked):
    a, _ = stocked
    a.is_archived = True
    a.save(update_fields=["is_archived"])
    assert ds.headline_numbers()["active_items"] == 1


def test_low_stock_tile_agrees_with_the_alerts_page(stocked, manager):
    """Both read the same query, so a dismissal moves both or neither."""
    _, b = stocked
    assert ds.headline_numbers()["low_stock_items"] == 1

    alert_service.dismiss(item=b, actor=manager)
    assert ds.headline_numbers()["low_stock_items"] == 0
    assert alert_service.alert_count() == 0


def test_items_moved_counts_items_not_movements(stocked, manager, warehouse):
    """Ten receipts of the same bolt is one item moving."""
    a, _ = stocked
    for _ in range(4):
        ss.record_receipt(actor=manager, item=a, location=warehouse, quantity=1)
    assert ds.headline_numbers()["items_moved_this_week"] == 2


def test_today_uses_the_business_day_not_utc(stocked, manager, warehouse):
    """The boundary is local midnight. Yesterday evening must not count as
    today, and this is the case a UTC comparison gets wrong."""
    a, _ = stocked
    before = ds.headline_numbers()["movements_today"]

    movement = ss.record_issue(actor=manager, item=a, location=warehouse, quantity=1)
    # Push it into yesterday, local time.
    yesterday = ds._local_day_start() - timedelta(hours=2)
    with immutability_disabled() as cur:
        cur.execute(
            "UPDATE stock_movement SET recorded_at = %s WHERE id = %s",
            [yesterday, movement.id],
        )

    assert ds.headline_numbers()["movements_today"] == before


def test_on_hand_by_category_includes_empty_categories(db, category):
    """A category with nothing in it is a real answer, arguably the more
    interesting one, so this must not be counted from the ledger outward."""
    Item.objects.create(sku="E-1", name="Empty", reorder_level=1, category=category)
    rows = ds.on_hand_by_category()
    assert rows == [{"label": category.name, "on_hand": 0}]


def test_on_hand_by_location_splits_the_total(stocked, warehouse, shop):
    rows = {row["label"]: row["on_hand"] for row in ds.on_hand_by_location()}
    assert rows[warehouse.code] == 50
    assert rows[shop.code] == 20
    assert sum(rows.values()) == ds.total_on_hand()


def test_transfer_moves_stock_between_locations_without_changing_the_total(
    stocked, manager, warehouse, shop
):
    a, _ = stocked
    before = ds.total_on_hand()
    ss.record_transfer(
        actor=manager, item=a, source=warehouse, destination=shop, quantity=10
    )
    rows = {row["label"]: row["on_hand"] for row in ds.on_hand_by_location()}
    assert rows[warehouse.code] == 40
    assert rows[shop.code] == 30
    assert ds.total_on_hand() == before


def test_weekly_series_has_one_point_per_week_including_empty_ones(stocked):
    """A chart that drops empty weeks compresses a quiet fortnight into a gap
    and makes the trend look steadier than it was."""
    series = ds.movement_volume_by_week()
    assert len(series) == ds.CHART_WEEKS
    weeks = [row["week"] for row in series]
    assert weeks == sorted(weeks)
    assert all(set(row) == {"week", "receipts", "issues", "movements"} for row in series)


def test_weekly_series_separates_receipts_from_issues(stocked, manager, warehouse):
    a, _ = stocked
    ss.record_issue(actor=manager, item=a, location=warehouse, quantity=7)

    current = ds.movement_volume_by_week()[-1]
    assert current["receipts"] == 70  # 50 + 20 opening receipts
    assert current["issues"] == 7


def test_weekly_series_ignores_transfers(stocked, manager, warehouse, shop):
    """A transfer changes no total, so counting it as either would stop the
    two lines meaning "stock in" and "stock out"."""
    a, _ = stocked
    before = ds.movement_volume_by_week()[-1]
    ss.record_transfer(
        actor=manager, item=a, source=warehouse, destination=shop, quantity=5
    )
    after = ds.movement_volume_by_week()[-1]
    assert after["receipts"] == before["receipts"]
    assert after["issues"] == before["issues"]
    # It is still activity, so the movement count does rise.
    assert after["movements"] == before["movements"] + 1


def test_recent_movements_are_newest_first(stocked, manager, warehouse):
    a, _ = stocked
    latest = ss.record_issue(actor=manager, item=a, location=warehouse, quantity=1)
    assert ds.recent_movements()[0].id == latest.id
