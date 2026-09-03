"""The seed command has to survive being run on every deploy.

It is the only code in the project that disables an immutability trigger, so
the most important assertion here is not that it produced data -- it is that
the triggers are back on afterwards.
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from apps.catalog.models import Item, ItemTimelineEvent
from apps.stock.models import LedgerEntry, StockMovement


def triggers_enabled():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT tgname, tgenabled FROM pg_trigger "
            "WHERE NOT tgisinternal AND tgname LIKE '%%immutable' "
            "ORDER BY tgname"
        )
        return dict(cur.fetchall())


@pytest.fixture
def seeded(db, manager):
    call_command("seed_demo_data", verbosity=0)


def test_creates_items_and_movements(seeded):
    assert Item.objects.count() == 25
    assert StockMovement.objects.count() >= 25


def test_immutability_triggers_are_re_enabled(seeded):
    """'O' is "origin", the normal enabled state. 'D' is disabled.

    Asserted over every immutability trigger rather than the two the command
    touches, so that adding a third append-only table later is covered here
    for free instead of silently escaping the check.
    """
    states = triggers_enabled()
    assert states, "no immutability triggers found at all"
    assert set(states.values()) == {"O"}, states


def test_ledger_never_goes_negative(seeded):
    """Every movement went through stock_service, so no item/location pair may
    hold a negative balance. A seed writing rows directly could produce one."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT item_id, location_id, SUM(delta) FROM stock_ledger_entry "
            "GROUP BY item_id, location_id HAVING SUM(delta) < 0"
        )
        assert cur.fetchall() == []


def test_transfers_are_balanced(seeded):
    """Each transfer writes exactly two entries summing to zero -- stock moved,
    not created."""
    for movement in StockMovement.objects.filter(kind="TRANSFER"):
        entries = LedgerEntry.objects.filter(movement=movement)
        assert entries.count() == 2
        assert sum(e.delta for e in entries) == 0


def test_produces_low_stock_and_archived_examples(seeded):
    """The filters need something to find, or the demo shows empty states."""
    low = [i for i in Item.objects.with_on_hand() if i.on_hand <= i.reorder_level]
    assert low, "no item is at or below its reorder level"
    assert Item.objects.filter(is_archived=True).exists()


def test_is_idempotent(seeded):
    """Runs on every deploy. A second run must not double the quantities."""
    before = StockMovement.objects.count()
    call_command("seed_demo_data", verbosity=0)
    assert StockMovement.objects.count() == before
    assert Item.objects.count() == 25


@pytest.mark.django_db
def test_reset_reseeds_even_when_other_items_exist(db, settings, manager, category):
    """The skip check asks whether this seed has run, not whether the table is
    empty. Getting that wrong made --reset delete without restoring."""
    settings.DEBUG = True
    Item.objects.create(
        sku="REAL-2", name="Not seeded", reorder_level=1, category=category
    )
    call_command("seed_demo_data", verbosity=0)
    assert Item.objects.count() == 26


def test_opening_stock_predates_everything_it_supplies(seeded):
    """Stock cannot be issued before it arrives.

    The opening receipts are written first but carry auto_now_add timestamps,
    so unless they are explicitly backdated they land at "now" -- after every
    movement that consumed them. The balances still add up, but the history
    reads as impossible, which defeats the point of routing the seed through
    the service layer at all.
    """
    for item in Item.objects.all():
        movements = list(
            StockMovement.objects.filter(item=item).order_by("recorded_at", "id")
        )
        if len(movements) < 2:
            continue
        first = movements[0]
        assert first.note == "Opening stock", (
            f"{item.sku}: earliest movement is a {first.kind} at "
            f"{first.recorded_at}, not the opening receipt"
        )


def test_ledger_balance_never_goes_negative_in_time_order(seeded):
    """Replaying the ledger chronologically must never dip below zero.

    Stronger than summing the final balance: a history can finish positive
    while having passed through an impossible negative along the way.
    """
    running: dict[tuple[int, int], int] = {}
    for entry in LedgerEntry.objects.order_by("occurred_at", "id"):
        key = (entry.item_id, entry.location_id)
        running[key] = running.get(key, 0) + entry.delta
        assert running[key] >= 0, (
            f"item {entry.item_id} at location {entry.location_id} "
            f"hit {running[key]} on {entry.occurred_at}"
        )


def test_items_are_created_before_their_first_movement(seeded):
    """An item cannot have history from before it existed.

    Cosmetic next to the ledger ordering -- no balance is wrong -- but goal
    9's page is the one claiming this record is trustworthy, and "created
    today" above two months of movements undercuts that at a glance.
    """
    for item in Item.objects.all():
        first = (
            StockMovement.objects.filter(item=item)
            .order_by("recorded_at")
            .values_list("recorded_at", flat=True)
            .first()
        )
        if first is None:
            continue
        assert item.created_at < first, (
            f"{item.sku}: created {item.created_at}, first movement {first}"
        )

        created_event = ItemTimelineEvent.objects.filter(
            item=item, event_type="CREATED"
        ).first()
        if created_event:
            assert created_event.created_at < first, (
                f"{item.sku}: CREATED event is after the first movement"
            )


def test_timeline_events_are_spread_not_bunched(seeded):
    """The item with a full history should read as activity over time."""
    item = Item.objects.get(sku="A-100")
    stamps = list(
        ItemTimelineEvent.objects.filter(item=item)
        .order_by("created_at")
        .values_list("created_at", flat=True)
    )
    assert len(stamps) >= 4, stamps
    # Not all on the same day, which is what auto_now_add produced before.
    assert len({s.date() for s in stamps}) > 1, stamps


@pytest.mark.django_db
def test_reset_refuses_to_run_in_production(settings, manager):
    """The guard on the most dangerous code in the project."""
    call_command("seed_demo_data", verbosity=0)
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DEBUG=False"):
        call_command("seed_demo_data", "--reset", verbosity=0)

    # And nothing was deleted on the way to refusing.
    assert Item.objects.count() == 25


@pytest.mark.django_db
def test_reset_only_deletes_seeded_skus(db, settings, manager, category):
    """Data this command did not create must survive a reset."""
    # The suite runs with DEBUG=False, so --reset refuses by default. That is
    # the guard doing its job; opt in here rather than weakening it.
    settings.DEBUG = True
    call_command("seed_demo_data", verbosity=0)
    keeper = Item.objects.create(
        sku="REAL-1", name="Not seeded", reorder_level=1, category=category
    )

    call_command("seed_demo_data", "--reset", verbosity=0)

    assert Item.objects.filter(pk=keeper.pk).exists()
    # Reset then reseeds, so the 25 are back -- plus the one it left alone.
    assert Item.objects.count() == 26


@pytest.mark.django_db
def test_reset_leaves_triggers_enabled(db, settings, manager):
    settings.DEBUG = True
    call_command("seed_demo_data", verbosity=0)
    call_command("seed_demo_data", "--reset", verbosity=0)
    assert set(triggers_enabled().values()) == {"O"}
