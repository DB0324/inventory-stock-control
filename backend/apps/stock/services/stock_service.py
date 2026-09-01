"""The only place stock movements are written.

Views, CSV imports and the seed command all come through here. That is
deliberate: the negative-stock rule, the location check and the archived-item
check each exist once, so there is no path that enforces two of the three.
"""

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce

from apps.stock.models import LedgerEntry, Location, MovementKind, StockMovement

from .exceptions import InsufficientStock, ItemArchived, LocationNotAssigned

# Arbitrary but fixed. Advisory locks are global to the database, so this
# namespace keeps ours from colliding with anything else that might use them.
LOCK_NAMESPACE = 4711


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def on_hand(item, location=None) -> int:
    """Current quantity, always derived. Nothing stores this number.

    Pass a location for that shelf; omit it for the total across every
    location, which is what the low-stock check compares against.
    """
    qs = LedgerEntry.objects.filter(item=item)
    if location is not None:
        qs = qs.filter(location=location)
    return qs.aggregate(total=Coalesce(Sum("delta"), 0))["total"]


# --------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------

def _assert_not_archived(item):
    if item.is_archived:
        raise ItemArchived(f"{item.sku} is archived and cannot take new movements.")


def _assert_can_act_at(user, location):
    """Managers act everywhere. Staff only where they are assigned.

    Managers hold no LocationAssignment rows at all, so their access can never
    be revoked by someone deleting one.
    """
    if user.is_manager:
        return
    assigned = user.location_assignments.filter(location=location).exists()
    if not assigned:
        raise LocationNotAssigned(f"You are not assigned to {location.code}.")


def _lock(item_id: int, *location_ids: int) -> None:
    """Serialise writers on each (item, location) pair.

    Three details here are load-bearing:

    1. Advisory rather than SELECT ... FOR UPDATE. There is no row holding
       "item 42's balance at WH" -- that is the whole design -- so there is
       nothing to lock. FOR UPDATE locks rows that already exist and does
       nothing to stop a concurrent INSERT.

    2. sorted(). A transfer WH->SF and a simultaneous SF->WH on the same item
       would otherwise grab their locks in opposite orders and deadlock.
       Sorted, both take the lower id first and one simply waits.

    3. _xact_, not the session-scoped variant. Transaction-scoped locks
       release on commit or rollback. Session ones need an explicit unlock,
       so a crash in between wedges that pair until the connection dies. It
       also happens to be the only variant that survives PgBouncer's
       transaction pooling, which is what Neon gives us.
    """
    with connection.cursor() as cur:
        for location_id in sorted(set(location_ids)):
            key = (item_id * 100_003 + location_id) % 2_147_483_647
            cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", [LOCK_NAMESPACE, key])


def _write(*, item, kind, quantity, actor, entries, location=None,
           source=None, destination=None, reason=None, note=""):
    """Insert one movement and its entries. Assumes locks are already held."""
    movement = StockMovement.objects.create(
        item=item,
        kind=kind,
        quantity=quantity,
        location=location,
        source_location=source,
        destination_location=destination,
        reason=reason,
        note=note,
        recorded_by=actor,
    )
    LedgerEntry.objects.bulk_create([
        LedgerEntry(
            movement=movement,
            item=item,
            location=loc,
            delta=delta,
            occurred_at=movement.recorded_at,
        )
        for loc, delta in entries
    ])
    return movement


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

@transaction.atomic
def record_receipt(*, actor, item, location, quantity, note=""):
    """Stock arrives. One entry, positive."""
    _assert_not_archived(item)
    _assert_can_act_at(actor, location)
    if quantity <= 0:
        raise ValueError("Quantity must be positive.")

    return _write(
        item=item, kind=MovementKind.RECEIPT, quantity=quantity, actor=actor,
        location=location, note=note, entries=[(location, quantity)],
    )


@transaction.atomic
def record_issue(*, actor, item, location, quantity, note=""):
    """Stock leaves. One entry, negative, and it may not go below zero."""
    _assert_not_archived(item)
    _assert_can_act_at(actor, location)
    if quantity <= 0:
        raise ValueError("Quantity must be positive.")

    _lock(item.id, location.id)

    available = on_hand(item, location)
    if available < quantity:
        raise InsufficientStock(
            f"{location.code} holds {available}; cannot issue {quantity}."
        )

    return _write(
        item=item, kind=MovementKind.ISSUE, quantity=quantity, actor=actor,
        location=location, note=note, entries=[(location, -quantity)],
    )


@transaction.atomic
def record_adjustment(*, actor, item, location, quantity, reason, note=""):
    """A correction. quantity is signed, and a reason is mandatory.

    The reason is required in three places -- the form, here, and a database
    CHECK. The form gives a good message; the CHECK makes it true.
    """
    _assert_not_archived(item)
    _assert_can_act_at(actor, location)
    if quantity == 0:
        raise ValueError("Adjustment quantity cannot be zero.")
    if not reason or not reason.strip():
        raise ValueError("Adjustments must carry a reason.")

    _lock(item.id, location.id)

    if quantity < 0:
        available = on_hand(item, location)
        if available + quantity < 0:
            raise InsufficientStock(
                f"{location.code} holds {available}; cannot adjust by {quantity}."
            )

    return _write(
        item=item, kind=MovementKind.ADJUSTMENT, quantity=quantity, actor=actor,
        location=location, reason=reason.strip(), note=note,
        entries=[(location, quantity)],
    )


@transaction.atomic
def record_transfer(*, actor, item, source, destination, quantity, note=""):
    """Stock moves between locations. Two entries, one transaction.

    The two entries are what makes this indivisible. If the second insert
    fails, the first and the movement both roll back -- so the "logged at the
    sending end, never at the receiving end" failure is not something we avoid
    by being careful, it is something the transaction makes impossible.
    """
    _assert_not_archived(item)
    _assert_can_act_at(actor, source)
    _assert_can_act_at(actor, destination)
    if source.id == destination.id:
        raise ValueError("Source and destination must differ.")
    if quantity <= 0:
        raise ValueError("Quantity must be positive.")

    _lock(item.id, source.id, destination.id)

    available = on_hand(item, source)
    if available < quantity:
        raise InsufficientStock(
            f"{source.code} holds {available}; cannot transfer {quantity}."
        )

    return _write(
        item=item, kind=MovementKind.TRANSFER, quantity=quantity, actor=actor,
        source=source, destination=destination, note=note,
        entries=[(source, -quantity), (destination, quantity)],
    )