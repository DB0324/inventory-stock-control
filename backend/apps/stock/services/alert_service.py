"""Low-stock alerts (goal 10).

An item alerts when its on-hand quantity, summed across every location, sits
at or below its reorder level. A manager can dismiss one, and the dismissal
lapses if the item recovers and then falls back.

Nothing here stores an "is alerting" flag. Alerting is derived from the ledger
the same way every other quantity in this system is -- a flag would be a second
source of truth that drifts the moment a movement is recorded by any path that
forgot to update it.
"""

from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.catalog.models import Item
from apps.stock.models import LowStockDismissal


def active_alerts():
    """Items that should appear in the alerts area, newest shortage first.

    Archived items are excluded. They reject new movements and drop out of the
    day-to-day lists, so alerting about stock nobody can act on would be noise
    a manager cannot clear.
    """
    live_dismissal = LowStockDismissal.objects.filter(
        item=OuterRef("pk"),
        cleared_at__isnull=True,
        # Matched against the item's *current* threshold. If a manager raises
        # the reorder level after dismissing, the item is now low against a
        # bar nobody has acknowledged, so the old dismissal stops applying.
        reorder_level=OuterRef("reorder_level"),
    )
    return (
        Item.objects.filter(is_archived=False)
        .select_related("category")
        .with_on_hand()
        .at_or_below_reorder()
        .annotate(is_dismissed=Exists(live_dismissal))
        .filter(is_dismissed=False)
        # Deepest shortage first: an item at zero matters more than one a
        # single unit under its level. id breaks ties so pages are stable.
        .order_by("on_hand", "name", "id")
    )


def alert_count():
    """For the navigation badge."""
    return active_alerts().count()


def dismiss(*, item, actor):
    """Acknowledge one item's alert.

    Idempotent: dismissing twice leaves the first row alone rather than
    creating a second, which the partial unique index would reject anyway.
    The stored reorder_level is the item's threshold right now, which is what
    the dismissal is actually about.
    """
    dismissal, _ = LowStockDismissal.objects.get_or_create(
        item=item,
        cleared_at=None,
        reorder_level=item.reorder_level,
        defaults={"dismissed_by": actor},
    )
    return dismissal


def clear_if_recovered(item):
    """Re-arm the alert once stock climbs back above the reorder level.

    Called from stock_service on every write, so the cost is one aggregate per
    movement. The alternative -- deciding "did it ever recover?" by replaying
    every ledger entry since the dismissal -- gives the same answer but pays
    for history the system can already summarise in one query.

    Cleared rows are kept rather than deleted. "This was dismissed on Tuesday
    and came back on Friday" is exactly the kind of question an audit asks.
    """
    # Imported here rather than at module scope: stock_service calls into this
    # module, so a top-level import in either direction closes a cycle.
    from apps.stock.services import stock_service as ss

    if ss.on_hand(item) <= item.reorder_level:
        return 0

    return LowStockDismissal.objects.filter(
        item=item, cleared_at__isnull=True
    ).update(cleared_at=timezone.now())
