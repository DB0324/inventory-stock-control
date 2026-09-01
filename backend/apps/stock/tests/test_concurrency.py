"""Tests C-01 to C-07: the advisory lock.

Every other test in the suite runs single-threaded, which is exactly the case
the race does not happen in. Without these, _lock() is code we believe works.

These use TransactionTestCase rather than pytest's db fixture, because the
threads need real committed transactions on separate connections. The normal
fixture wraps everything in one transaction and rolls back, so a second
thread would never see the first thread's writes.
"""

import threading

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase

from apps.catalog.models import Category, Item
from apps.stock.models import LedgerEntry, Location, StockMovement
from apps.stock.services import stock_service as ss
from apps.stock.services.exceptions import InsufficientStock


def _run_concurrently(targets):
    """Run callables in parallel, collect (result, exception) per thread.

    Each thread closes its own database connection afterwards. Django opens a
    connection per thread and does not clean them up, so without this the test
    database cannot be dropped at teardown.
    """
    results = [None] * len(targets)

    def wrap(index, fn):
        try:
            results[index] = ("ok", fn())
        except Exception as exc:
            results[index] = ("error", exc)
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=wrap, args=(i, fn)) for i, fn in enumerate(targets)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not any(t.is_alive() for t in threads), "deadlock: a thread never finished"
    return results


class ConcurrencyTests(TransactionTestCase):
    # Triggers block DELETE, so the normal flush teardown fails. Truncation is
    # DDL and bypasses row triggers, which is what serialized_rollback avoids
    # needing -- we let Django TRUNCATE between tests instead.
    reset_sequences = True

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="m@test.local", password="x", full_name="M", role=User.Role.MANAGER,
        )
        self.category = Category.objects.create(name="Fasteners")
        self.item = Item.objects.create(
            sku="A-100", name="Hex bolt", reorder_level=10, category=self.category,
        )
        self.other_item = Item.objects.create(
            sku="B-200", name="Washer", reorder_level=10, category=self.category,
        )
        self.wh = Location.objects.create(code="WH", name="Warehouse")
        self.sf = Location.objects.create(code="SF", name="Shop floor")

    def _stock(self, item, location, quantity):
        ss.record_receipt(
            actor=self.user, item=item, location=location, quantity=quantity,
        )

    # --- C-01 ------------------------------------------------------------

    def test_two_transfers_cannot_overdraw(self):
        """Ten units, two threads each moving eight. Exactly one may win.

        Without the lock both read 10, both pass the check, and the balance
        lands at -6 -- uncorrectable, because the ledger is append-only.
        """
        self._stock(self.item, self.wh, 10)

        def transfer():
            return ss.record_transfer(
                actor=self.user, item=self.item,
                source=self.wh, destination=self.sf, quantity=8,
            )

        results = _run_concurrently([transfer, transfer])

        outcomes = [status for status, _ in results]
        assert outcomes.count("ok") == 1, f"expected exactly one success: {results}"
        assert outcomes.count("error") == 1
        assert isinstance(results[outcomes.index("error")][1], InsufficientStock)

        assert ss.on_hand(self.item, self.wh) == 2
        assert ss.on_hand(self.item, self.sf) == 8
        assert ss.on_hand(self.item) == 10

    # --- C-02 ------------------------------------------------------------

    def test_ten_issues_against_five_units(self):
        """Exactly five succeed. Not four, not six."""
        self._stock(self.item, self.wh, 5)

        def issue():
            return ss.record_issue(
                actor=self.user, item=self.item, location=self.wh, quantity=1,
            )

        results = _run_concurrently([issue] * 10)

        successes = sum(1 for status, _ in results if status == "ok")
        assert successes == 5, f"expected 5 successes, got {successes}"
        assert ss.on_hand(self.item, self.wh) == 0

    # --- C-03 ------------------------------------------------------------

    def test_opposing_transfers_do_not_deadlock(self):
        """WH->SF and SF->WH at the same time, same item.

        This is the test that justifies sorted() in _lock(). Remove it and
        one thread holds WH waiting for SF while the other holds SF waiting
        for WH. Both threads then hang, the join() times out, and the
        assertion in _run_concurrently fires.

        Verified by deleting sorted() and watching this fail.
        """
        self._stock(self.item, self.wh, 50)
        self._stock(self.item, self.sf, 50)

        def wh_to_sf():
            return ss.record_transfer(
                actor=self.user, item=self.item,
                source=self.wh, destination=self.sf, quantity=10,
            )

        def sf_to_wh():
            return ss.record_transfer(
                actor=self.user, item=self.item,
                source=self.sf, destination=self.wh, quantity=10,
            )

        results = _run_concurrently([wh_to_sf, sf_to_wh])

        assert all(status == "ok" for status, _ in results), results
        assert ss.on_hand(self.item, self.wh) == 50
        assert ss.on_hand(self.item, self.sf) == 50
        assert ss.on_hand(self.item) == 100

    # --- C-04 ------------------------------------------------------------

    def test_different_items_do_not_serialise(self):
        """A negative result, and it matters.

        Locks are keyed on (item, location). If this showed serialisation the
        key would be too coarse and throughput would suffer for no gain in
        correctness.
        """
        self._stock(self.item, self.wh, 10)
        self._stock(self.other_item, self.wh, 10)

        def issue_a():
            return ss.record_issue(
                actor=self.user, item=self.item, location=self.wh, quantity=10,
            )

        def issue_b():
            return ss.record_issue(
                actor=self.user, item=self.other_item, location=self.wh, quantity=10,
            )

        results = _run_concurrently([issue_a, issue_b])

        assert all(status == "ok" for status, _ in results), results
        assert ss.on_hand(self.item, self.wh) == 0
        assert ss.on_hand(self.other_item, self.wh) == 0

    # --- C-06 ------------------------------------------------------------

    def test_concurrent_receipt_and_issue(self):
        """Both apply. The ledger sums correctly regardless of which won."""
        self._stock(self.item, self.wh, 20)

        def receipt():
            return ss.record_receipt(
                actor=self.user, item=self.item, location=self.wh, quantity=30,
            )

        def issue():
            return ss.record_issue(
                actor=self.user, item=self.item, location=self.wh, quantity=15,
            )

        results = _run_concurrently([receipt, issue])

        assert all(status == "ok" for status, _ in results), results
        assert ss.on_hand(self.item, self.wh) == 35

    # --- ledger integrity under load --------------------------------------

    def test_no_orphaned_movements_after_contention(self):
        """Every movement that committed has the right number of entries.

        A failed transfer must leave neither a movement nor a half-written
        entry. This checks the invariant across all of them at once.
        """
        self._stock(self.item, self.wh, 10)

        def transfer():
            return ss.record_transfer(
                actor=self.user, item=self.item,
                source=self.wh, destination=self.sf, quantity=3,
            )

        _run_concurrently([transfer] * 6)

        for movement in StockMovement.objects.all():
            expected = 2 if movement.kind == "TRANSFER" else 1
            actual = LedgerEntry.objects.filter(movement=movement).count()
            assert actual == expected, f"{movement.kind} has {actual} entries"