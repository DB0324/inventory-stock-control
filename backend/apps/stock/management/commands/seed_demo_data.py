"""Populates a database with something worth clicking through.

Runs on every deploy, so it must be idempotent -- it checks for existing data
and does nothing rather than doubling every quantity.

Every movement goes through stock_service. A seed that inserts ledger rows
directly can build a state the application could never reach, and then the app
looks fine against a world that cannot happen: negative stock, a transfer with
one leg, an issue from a location nobody is assigned to.
"""

import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from apps.catalog.models import Category, Item
from apps.catalog.services import timeline_service as ts
from apps.stock.models import Location, LocationAssignment, StockMovement
from apps.stock.services import stock_service as ss
from apps.stock.services.exceptions import InsufficientStock

CATEGORIES = ["Fasteners", "Electrical", "Plumbing", "Safety gear"]

LOCATIONS = [
    ("WH", "Main warehouse"),
    ("SF", "Shop floor"),
    ("ST", "Site store"),
]

ITEMS = [
    ("A-100", "Hex bolt M8 x 40", "Fasteners", "EA", 50),
    ("A-101", "Hex bolt M10 x 60", "Fasteners", "EA", 40),
    ("A-102", "Wing nut M8", "Fasteners", "EA", 100),
    ("A-103", "Washer M8 flat", "Fasteners", "EA", 200),
    ("A-104", "Self-tapping screw 4mm", "Fasteners", "BOX", 15),
    ("A-105", "Coach bolt M12", "Fasteners", "EA", 25),
    ("A-106", "Threaded rod M10 1m", "Fasteners", "EA", 10),
    ("E-200", "Twin and earth 2.5mm 100m", "Electrical", "ROLL", 5),
    ("E-201", "Consumer unit 10-way", "Electrical", "EA", 3),
    ("E-202", "MCB 32A type B", "Electrical", "EA", 20),
    ("E-203", "Socket outlet double", "Electrical", "EA", 30),
    ("E-204", "Junction box 4-term", "Electrical", "EA", 25),
    ("E-205", "Cable clip 2.5mm", "Electrical", "BOX", 10),
    ("E-206", "Earth sleeving 3mm", "Electrical", "ROLL", 8),
    ("P-300", "Copper pipe 15mm 3m", "Plumbing", "EA", 20),
    ("P-301", "Compression elbow 15mm", "Plumbing", "EA", 40),
    ("P-302", "PTFE tape 12mm", "Plumbing", "EA", 30),
    ("P-303", "Isolating valve 15mm", "Plumbing", "EA", 15),
    ("P-304", "Push-fit tee 22mm", "Plumbing", "EA", 12),
    ("P-305", "Pipe insulation 15mm 1m", "Plumbing", "EA", 25),
    ("S-400", "Safety glasses clear", "Safety gear", "EA", 20),
    ("S-401", "Work gloves size L", "Safety gear", "PAIR", 30),
    ("S-402", "Hard hat white", "Safety gear", "EA", 10),
    ("S-403", "Hi-vis vest size L", "Safety gear", "EA", 15),
    ("S-404", "Ear defenders", "Safety gear", "EA", 8),
]

# Fixed, so a redeploy produces the same demo database rather than a new
# random one every time. A reviewer comparing two visits should see the same
# numbers.
RANDOM_SEED = 20260903

WEEKS_OF_HISTORY = 8


class Command(BaseCommand):
    help = "Seed categories, locations, items and eight weeks of movements."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Seed even if items already exist. Adds movements on top.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()

        manager = User.objects.filter(role=User.Role.MANAGER).first()
        if manager is None:
            self.stderr.write("No manager found. Run create_demo_users first.")
            return

        if Item.objects.exists() and not options["force"]:
            self.stdout.write("Items already exist; nothing to do.")
            return

        random.seed(RANDOM_SEED)

        locations = {
            code: Location.objects.get_or_create(code=code, defaults={"name": name})[0]
            for code, name in LOCATIONS
        }
        categories = {
            name: Category.objects.get_or_create(name=name)[0] for name in CATEGORIES
        }

        # Staff get different location sets, so a reviewer signing in as staff
        # can see goal 5's scoping actually restricting something rather than
        # taking the tests' word for it.
        self._assign_staff(User, manager, locations)

        items = self._create_items(categories, manager)
        self._record_movements(items, list(locations.values()), manager)
        self._add_timeline_colour(items, manager)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(items)} items and "
                f"{StockMovement.objects.count()} movements."
            )
        )

    # ------------------------------------------------------------------

    def _assign_staff(self, User, manager, locations):
        staff = User.objects.filter(role=User.Role.STAFF).order_by("id")
        if not staff.exists():
            return
        # First staff member: warehouse only. Second, if present: shop floor
        # and site store. Neither can act everywhere, which is the point --
        # an assignment that covers everything demonstrates nothing.
        sets = [["WH"], ["SF", "ST"]]
        for user, codes in zip(staff, sets):
            for code in codes:
                LocationAssignment.objects.get_or_create(
                    user=user,
                    location=locations[code],
                    defaults={"assigned_by": manager},
                )

    def _create_items(self, categories, manager):
        items = []
        for sku, name, category, uom, reorder in ITEMS:
            # get_or_create, not create: --force runs against a database that
            # already holds these SKUs, and item_sku_ci_unique would reject a
            # blind insert. The timeline event is only written for genuinely
            # new items, so re-running does not invent a second "created".
            item, created = Item.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "category": categories[category],
                    "unit_of_measure": uom,
                    "reorder_level": reorder,
                    "description": f"{name}. Stocked line.",
                },
            )
            if created:
                ts.record_created(item=item, actor=manager)
            items.append(item)
        return items

    def _record_movements(self, items, locations, manager):
        """Eight weeks of activity, so the history has a shape rather than a
        single spike. Opening receipts land first, then a mix of issues and
        transfers spread across the period."""
        now = timezone.now()
        warehouse = locations[0]

        # Opening stock, deliberately uneven so that some items finish below
        # their reorder level and the low-stock filter has something to find.
        for index, item in enumerate(items):
            if index % 8 == 0:
                opening = max(1, item.reorder_level // 3)  # will read as low
            elif index % 5 == 0:
                opening = item.reorder_level  # exactly at the level: lte, not lt
            else:
                opening = item.reorder_level * random.randint(3, 6)
            ss.record_receipt(
                actor=manager,
                item=item,
                location=warehouse,
                quantity=opening,
                note="Opening stock",
            )

        recent = []
        for _ in range(140):
            item = random.choice(items)
            kind = random.choices(
                ["issue", "transfer", "receipt"], weights=[5, 2, 3]
            )[0]
            try:
                if kind == "issue":
                    movement = ss.record_issue(
                        actor=manager,
                        item=item,
                        location=random.choice(locations),
                        quantity=random.randint(1, 5),
                        note="",
                    )
                elif kind == "transfer":
                    source, destination = random.sample(locations, 2)
                    movement = ss.record_transfer(
                        actor=manager,
                        item=item,
                        source=source,
                        destination=destination,
                        quantity=random.randint(1, 5),
                    )
                else:
                    movement = ss.record_receipt(
                        actor=manager,
                        item=item,
                        location=random.choice(locations),
                        quantity=random.randint(5, 30),
                        note="",
                    )
            except InsufficientStock:
                # Expected. The seed does not track balances, so some issues
                # and transfers are legitimately refused. Skipping them is the
                # correct response -- forcing them through would mean
                # bypassing the guard the whole design rests on, and the demo
                # database would then contain a state the app cannot produce.
                continue
            recent.append(movement.id)

        self._backdate(recent, now)

    def _backdate(self, movement_ids, now):
        """Spread timestamps across the history window.

        recorded_at is auto_now_add, so it cannot be set through the service.
        This is the one place in the project that disables an immutability
        trigger, and it is confined to a seed command that only ever runs
        against a demo database.

        The try/finally is not defensive habit: a disabled immutability
        trigger is the worst state to leave a database in, because everything
        looks healthy and nothing is actually protected. Being inside
        handle()'s atomic block means a crash would roll the ALTERs back
        anyway, but relying on that alone would make the safety implicit.
        """
        if not movement_ids:
            return

        with connection.cursor() as cur:
            # Postgres refuses ALTER TABLE on a table with pending trigger
            # events, and every insert above queued one: Django creates
            # foreign keys as DEFERRABLE INITIALLY DEFERRED, so their checks
            # are still sitting in the queue at this point in the transaction.
            # This forces them to run now and empties it. Without this line
            # the command dies with "cannot ALTER TABLE because it has pending
            # trigger events" -- on every deploy, not just under test.
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cur.execute(
                "ALTER TABLE stock_movement DISABLE TRIGGER "
                "stock_movement_immutable"
            )
            cur.execute(
                "ALTER TABLE stock_ledger_entry DISABLE TRIGGER "
                "stock_ledger_entry_immutable"
            )
            try:
                for movement_id in movement_ids:
                    when = now - timedelta(
                        days=random.randint(0, WEEKS_OF_HISTORY * 7 - 1),
                        # Business hours, so the timestamps read like a working
                        # day rather than a machine running at 3am.
                        hours=random.randint(8, 17),
                    )
                    cur.execute(
                        "UPDATE stock_movement SET recorded_at = %s WHERE id = %s",
                        [when, movement_id],
                    )
                    cur.execute(
                        "UPDATE stock_ledger_entry SET occurred_at = %s "
                        "WHERE movement_id = %s",
                        [when, movement_id],
                    )
            finally:
                cur.execute(
                    "ALTER TABLE stock_movement ENABLE TRIGGER "
                    "stock_movement_immutable"
                )
                cur.execute(
                    "ALTER TABLE stock_ledger_entry ENABLE TRIGGER "
                    "stock_ledger_entry_immutable"
                )

    def _add_timeline_colour(self, items, manager):
        """One item with a full history, so goal 9 has something to show."""
        item = items[0]
        before = ts.snapshot(item)
        item.reorder_level = 60
        item.save()
        ts.record_changes(item=item, actor=manager, before=before)

        ts.record_note(
            item=item,
            actor=manager,
            body="Supplier changed packaging to boxes of 50 from March.",
        )
        ts.record_note(
            item=item,
            actor=manager,
            body="Two boxes water damaged on the June delivery; adjusted out.",
        )

        # An archived item, so the archived filter has something to find and
        # the detail page has a case where the movement form refuses to draw.
        archived = items[-1]
        if not archived.is_archived:
            archived.is_archived = True
            archived.save(update_fields=["is_archived", "updated_at"])
            ts.record_archived(item=archived, actor=manager)
