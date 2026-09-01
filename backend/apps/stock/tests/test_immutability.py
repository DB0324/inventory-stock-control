"""Tests U-21 to U-29. The database refuses, not just the application."""

import pytest
from django.db import DatabaseError, connection

from apps.stock.models import ImmutabilityError, StockMovement
from apps.stock.services import stock_service as ss


@pytest.fixture
def movement(manager, item, warehouse):
    return ss.record_receipt(actor=manager, item=item, location=warehouse, quantity=50)


def test_model_refuses_save(movement):
    movement.quantity = 999
    with pytest.raises(ImmutabilityError):
        movement.save()


def test_model_refuses_delete(movement):
    with pytest.raises(ImmutabilityError):
        movement.delete()


def test_queryset_update_blocked_by_trigger(movement):
    """U-25. queryset.update() bypasses Model.save() entirely -- which is
    exactly why the guarantee has to live in the database."""
    with pytest.raises(DatabaseError):
        StockMovement.objects.filter(pk=movement.pk).update(quantity=999)


def test_raw_sql_update_blocked(movement):
    with pytest.raises(DatabaseError), connection.cursor() as cur:
        cur.execute("UPDATE stock_movement SET quantity = 999 WHERE id = %s", [movement.pk])


def test_raw_sql_delete_blocked(movement):
    with pytest.raises(DatabaseError), connection.cursor() as cur:
        cur.execute("DELETE FROM stock_ledger_entry WHERE movement_id = %s", [movement.pk])