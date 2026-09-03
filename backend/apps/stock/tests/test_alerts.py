"""Low-stock alerts (goal 10).

The interesting requirement is the last sentence: a dismissed alert must come
back if the item rises above its reorder level and then falls to or below it
again. That is a cycle, not a state, so most of these tests walk it.
"""

import pytest

from apps.catalog.models import Item
from apps.stock.models import LowStockDismissal
from apps.stock.services import alert_service, stock_service as ss


@pytest.fixture
def low_item(db, manager, warehouse, category):
    """Reorder level 10, five on hand -- alerting from the start."""
    item = Item.objects.create(
        sku="LOW-1", name="Low stock item", reorder_level=10, category=category
    )
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=5, note="")
    return item


def skus(queryset):
    return [item.sku for item in queryset]


def test_item_at_or_below_reorder_alerts(low_item):
    assert skus(alert_service.active_alerts()) == ["LOW-1"]


def test_exactly_at_reorder_level_alerts(db, manager, warehouse, category):
    """'At or below' is the brief's wording, so equality counts."""
    item = Item.objects.create(
        sku="EXACT-1", name="Exactly at level", reorder_level=10, category=category
    )
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=10, note="")
    assert skus(alert_service.active_alerts()) == ["EXACT-1"]


def test_item_with_no_movements_alerts(db, category):
    """Zero on hand is at or below any non-negative reorder level.

    This is the case a LEFT JOIN without Coalesce silently drops -- an item
    nobody has ever received is exactly the one worth alerting about.
    """
    Item.objects.create(
        sku="NEVER-1", name="Never received", reorder_level=5, category=category
    )
    assert "NEVER-1" in skus(alert_service.active_alerts())


def test_alert_counts_stock_across_every_location(db, manager, warehouse, shop, category):
    """The brief says summed across every location, so 6 at each of two
    locations does not alert against a reorder level of 10."""
    item = Item.objects.create(
        sku="SPREAD-1", name="Spread thin", reorder_level=10, category=category
    )
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=6, note="")
    ss.record_receipt(actor=manager, item=item, location=shop, quantity=6, note="")
    assert "SPREAD-1" not in skus(alert_service.active_alerts())


def test_archived_items_do_not_alert(low_item):
    """They reject new movements, so a manager could not clear the alert."""
    low_item.is_archived = True
    low_item.save(update_fields=["is_archived"])
    assert skus(alert_service.active_alerts()) == []


def test_dismissal_hides_the_alert(low_item, manager):
    alert_service.dismiss(item=low_item, actor=manager)
    assert skus(alert_service.active_alerts()) == []


def test_dismissal_is_idempotent(low_item, manager):
    """The partial unique index would reject a second live row anyway."""
    alert_service.dismiss(item=low_item, actor=manager)
    alert_service.dismiss(item=low_item, actor=manager)
    assert LowStockDismissal.objects.filter(item=low_item).count() == 1


def test_alert_returns_after_recovery_and_a_second_fall(low_item, manager, warehouse):
    """The full cycle, which is the whole point of goal 10's last sentence."""
    alert_service.dismiss(item=low_item, actor=manager)
    assert skus(alert_service.active_alerts()) == []

    # Rises above the reorder level: 5 -> 25.
    ss.record_receipt(actor=manager, item=low_item, location=warehouse, quantity=20, note="")
    assert skus(alert_service.active_alerts()) == []  # not low, so still nothing

    # Falls back to or below it: 25 -> 8.
    ss.record_issue(actor=manager, item=low_item, location=warehouse, quantity=17, note="")
    assert skus(alert_service.active_alerts()) == ["LOW-1"]


def test_dismissal_survives_movements_that_do_not_recover(low_item, manager, warehouse):
    """Topping up from 5 to 9 against a level of 10 is not a recovery, so the
    manager should not be nagged again about something they acknowledged."""
    alert_service.dismiss(item=low_item, actor=manager)
    ss.record_receipt(actor=manager, item=low_item, location=warehouse, quantity=4, note="")
    assert skus(alert_service.active_alerts()) == []


def test_recovery_clears_rather_than_deletes_the_dismissal(low_item, manager, warehouse):
    """'Dismissed on Tuesday, back on Friday' is an audit question."""
    alert_service.dismiss(item=low_item, actor=manager)
    ss.record_receipt(actor=manager, item=low_item, location=warehouse, quantity=20, note="")

    dismissal = LowStockDismissal.objects.get(item=low_item)
    assert dismissal.cleared_at is not None
    assert dismissal.dismissed_by == manager


def test_raising_the_reorder_level_re_arms_a_dismissed_alert(low_item, manager):
    """The dismissal acknowledged one threshold. Move the bar and it is a
    different judgement, which nobody has made yet."""
    alert_service.dismiss(item=low_item, actor=manager)
    assert skus(alert_service.active_alerts()) == []

    low_item.reorder_level = 50
    low_item.save(update_fields=["reorder_level"])
    assert skus(alert_service.active_alerts()) == ["LOW-1"]


def test_lowering_the_reorder_level_below_stock_ends_the_alert(low_item):
    """No dismissal needed -- the item simply is not low any more."""
    low_item.reorder_level = 2
    low_item.save(update_fields=["reorder_level"])
    assert skus(alert_service.active_alerts()) == []


def test_deepest_shortage_sorts_first(db, manager, warehouse, category):
    empty = Item.objects.create(
        sku="Z-EMPTY", name="Nothing left", reorder_level=10, category=category
    )
    nearly = Item.objects.create(
        sku="A-NEARLY", name="Almost enough", reorder_level=10, category=category
    )
    ss.record_receipt(actor=manager, item=nearly, location=warehouse, quantity=9, note="")

    # Alphabetically A-NEARLY comes first; by shortage Z-EMPTY does.
    assert skus(alert_service.active_alerts()) == [empty.sku, nearly.sku]


def test_count_matches_the_list(low_item, db, category):
    Item.objects.create(
        sku="LOW-2", name="Another low one", reorder_level=5, category=category
    )
    assert alert_service.alert_count() == len(list(alert_service.active_alerts()))
    assert alert_service.alert_count() == 2


def test_transfer_does_not_change_alert_state(manager, item, warehouse, shop):
    """Goal 10 sums across every location, so moving stock between shelves
    cannot change whether an item is low. The total is identical before and
    after -- an aggregate scoped to one location would get this wrong.

    A transfer is the only movement kind where the write path runs and the
    global balance does not move, which makes it the shape that catches this.
    """
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=5)
    assert skus(alert_service.active_alerts()) == [item.sku]

    ss.record_transfer(
        actor=manager, item=item, source=warehouse, destination=shop, quantity=3
    )
    assert skus(alert_service.active_alerts()) == [item.sku]


def test_transfer_does_not_clear_a_dismissal(manager, item, warehouse, shop):
    """The damaging version of the same bug: a transfer must not look like a
    recovery. If it did, the manager would be re-nagged every time stock
    moved, about something they had already acknowledged."""
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=5)
    alert_service.dismiss(item=item, actor=manager)
    assert skus(alert_service.active_alerts()) == []

    ss.record_transfer(
        actor=manager, item=item, source=warehouse, destination=shop, quantity=3
    )
    assert skus(alert_service.active_alerts()) == []

    # And the dismissal is still live, not cleared-and-not-yet-re-alerting.
    assert LowStockDismissal.objects.get(item=item).cleared_at is None
