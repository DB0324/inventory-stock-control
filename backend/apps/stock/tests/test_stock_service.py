"""Tests U-01 to U-20: the ledger.

These are the ones where a bug is silent. A wrong sign in record_transfer
does not raise -- it produces a plausible number that is wrong forever.
"""

import pytest

from apps.stock.models import LedgerEntry, StockMovement
from apps.stock.services import stock_service as ss
from apps.stock.services.exceptions import (
    InsufficientStock, ItemArchived, LocationNotAssigned,
)


# --- Balances -------------------------------------------------------------

def test_receipt_increases_balance(manager, item, warehouse):
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=50)
    assert ss.on_hand(item, warehouse) == 50


def test_issue_decreases_balance(manager, item, warehouse):
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=50)
    ss.record_issue(actor=manager, item=item, location=warehouse, quantity=20)
    assert ss.on_hand(item, warehouse) == 30


def test_item_with_no_movements_is_zero(item, warehouse):
    """U-03. Not null, not an error -- zero. This is the Coalesce."""
    assert ss.on_hand(item, warehouse) == 0
    assert ss.on_hand(item) == 0


# --- Transfers ------------------------------------------------------------

def test_transfer_moves_stock_without_creating_it(manager, item, warehouse, shop):
    """U-04. The single most important assertion in the suite."""
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=50)
    ss.record_transfer(
        actor=manager, item=item, source=warehouse, destination=shop, quantity=20
    )
    assert ss.on_hand(item, warehouse) == 30
    assert ss.on_hand(item, shop) == 20
    assert ss.on_hand(item) == 50  # unchanged


def test_transfer_writes_two_entries_summing_to_zero(manager, item, warehouse, shop):
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=50)
    m = ss.record_transfer(
        actor=manager, item=item, source=warehouse, destination=shop, quantity=20
    )
    entries = LedgerEntry.objects.filter(movement=m)
    assert entries.count() == 2
    assert sum(e.delta for e in entries) == 0


def test_other_kinds_write_one_entry(manager, item, warehouse):
    m = ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=50)
    assert LedgerEntry.objects.filter(movement=m).count() == 1


def test_transfer_to_same_location_rejected(manager, item, warehouse):
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=50)
    with pytest.raises(ValueError):
        ss.record_transfer(
            actor=manager, item=item, source=warehouse,
            destination=warehouse, quantity=10,
        )


# --- The negative-stock guard --------------------------------------------

def test_transfer_beyond_balance_refused_and_writes_nothing(
    manager, item, warehouse, shop
):
    """U-07. The refusal must leave no trace -- a partial write would be
    worse than no check, because the ledger cannot be corrected."""
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=10)
    movements_before = StockMovement.objects.count()
    entries_before = LedgerEntry.objects.count()

    with pytest.raises(InsufficientStock):
        ss.record_transfer(
            actor=manager, item=item, source=warehouse,
            destination=shop, quantity=20,
        )

    assert StockMovement.objects.count() == movements_before
    assert LedgerEntry.objects.count() == entries_before
    assert ss.on_hand(item, warehouse) == 10


def test_issue_beyond_balance_refused(manager, item, warehouse):
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=10)
    with pytest.raises(InsufficientStock):
        ss.record_issue(actor=manager, item=item, location=warehouse, quantity=20)
    assert ss.on_hand(item, warehouse) == 10


def test_issue_refused_where_the_stock_is_somewhere_else(
    manager, item, warehouse, shop
):
    """Availability is per location, not global.

    The item genuinely has 10 units -- they are just at the warehouse. Issuing
    from the shop has to fail anyway, or the shop's balance goes negative and
    the two locations stop adding up to the total. This is the edge the
    global-balance version of the check would wave through.
    """
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=10)

    with pytest.raises(InsufficientStock):
        ss.record_issue(actor=manager, item=item, location=shop, quantity=1)

    assert ss.on_hand(item, shop) == 0
    assert ss.on_hand(item) == 10


def test_negative_adjustment_below_zero_refused(manager, item, warehouse):
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=5)
    with pytest.raises(InsufficientStock):
        ss.record_adjustment(
            actor=manager, item=item, location=warehouse,
            quantity=-10, reason="miscount",
        )


def test_error_message_names_the_actual_quantities(manager, item, warehouse):
    """A user standing at the shelf can act on 'holds 10'. They cannot act
    on 'insufficient stock'."""
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=10)
    with pytest.raises(InsufficientStock, match=r"WH holds 10.*cannot issue 20"):
        ss.record_issue(actor=manager, item=item, location=warehouse, quantity=20)


# --- Adjustments ----------------------------------------------------------

def test_adjustment_requires_reason(manager, item, warehouse):
    with pytest.raises(ValueError):
        ss.record_adjustment(
            actor=manager, item=item, location=warehouse, quantity=5, reason=None,
        )


def test_adjustment_rejects_whitespace_reason(manager, item, warehouse):
    with pytest.raises(ValueError):
        ss.record_adjustment(
            actor=manager, item=item, location=warehouse, quantity=5, reason="   ",
        )


def test_positive_adjustment_increases_balance(manager, item, warehouse):
    ss.record_adjustment(
        actor=manager, item=item, location=warehouse, quantity=7, reason="found",
    )
    assert ss.on_hand(item, warehouse) == 7


# --- Guards ---------------------------------------------------------------

def test_archived_item_rejects_movements(manager, item, warehouse):
    item.is_archived = True
    item.save()
    with pytest.raises(ItemArchived):
        ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=5)


@pytest.mark.parametrize("quantity", [0, -5])
def test_non_positive_receipt_rejected(manager, item, warehouse, quantity):
    with pytest.raises(ValueError):
        ss.record_receipt(
            actor=manager, item=item, location=warehouse, quantity=quantity,
        )


# --- Location scoping -----------------------------------------------------

def test_staff_can_act_at_assigned_location(staff_wh, item, warehouse):
    ss.record_receipt(actor=staff_wh, item=item, location=warehouse, quantity=5)
    assert ss.on_hand(item, warehouse) == 5


def test_staff_refused_at_unassigned_location(staff_wh, item, shop):
    with pytest.raises(LocationNotAssigned):
        ss.record_receipt(actor=staff_wh, item=item, location=shop, quantity=5)


def test_staff_transfer_checks_both_ends(manager, staff_wh, item, warehouse, shop):
    """U-20. Source is assigned, destination is not. Must still refuse."""
    ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=50)
    with pytest.raises(LocationNotAssigned):
        ss.record_transfer(
            actor=staff_wh, item=item, source=warehouse,
            destination=shop, quantity=10,
        )


def test_manager_acts_anywhere_without_assignment(manager, item, shop):
    ss.record_receipt(actor=manager, item=item, location=shop, quantity=5)
    assert ss.on_hand(item, shop) == 5