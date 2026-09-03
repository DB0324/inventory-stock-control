"""Populates a database with something worth clicking through.

Runs on every deploy, so it must be idempotent -- it checks for existing data
and does nothing rather than doubling every quantity.

Every movement goes through stock_service. A seed that inserts ledger rows
directly can build a state the application could never reach, and then the app
looks fine against a world that cannot happen: negative stock, a transfer with
one leg, an issue from a location nobody is assigned to.

Timestamps are the subtle part. recorded_at is auto_now_add, so the history has
to be backdated afterwards -- and the order that backdating produces is what a
reviewer actually reads. See the long note in _record_movements.
"""

import random
from contextlib import contextmanager
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.catalog.models import Category, Item, ItemTimelineEvent
from apps.catalog.services import timeline_service as ts
from apps.stock.models import (
    LedgerEntry,
    Location,
    LocationAssignment,
    StockMovement,
)
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

# What --reset is allowed to delete. Deliberately derived from the list above
# rather than "everything", so the command can never take data it did not
# create.
SEEDED_SKUS = [row[0] for row in ITEMS]

# Fixed, so a redeploy produces the same demo database rather than a new
# random one every time. A reviewer comparing two visits should see the same
# numbers.
RANDOM_SEED = 20260903

WEEKS_OF_HISTORY = 8
HISTORY_DAYS = WEEKS_OF_HISTORY * 7

# Every append-only table and the trigger guarding it, in one place -- so that
# adding a fourth means editing one list, and so nothing can be disabled
# without also being re-enabled.
IMMUTABLE_TRIGGERS = [
    ("stock_movement", "stock_movement_immutable"),
    ("stock_ledger_entry", "stock_ledger_entry_immutable"),
    ("catalog_item_timeline_event", "catalog_item_timeline_event_immutable"),
]


@contextmanager
def immutability_disabled():
    """Turn the append-only triggers off for the duration of the block.

    This is the most dangerous code in the project, so it is written once and
    reused rather than repeated at each call site.

    The finally is not defensive habit. A disabled immutability trigger is the
    worst state to leave a database in, because everything looks healthy and
    nothing is actually protected -- the guarantee is gone and nothing says so.
    Callers run inside an atomic block, so a crash would roll the ALTERs back
    anyway, but relying on that alone would make the safety implicit.
    """
    with connection.cursor() as cur:
        # Postgres refuses ALTER TABLE on a table with pending trigger events,
        # and Django creates foreign keys as DEFERRABLE INITIALLY DEFERRED, so
        # every insert so far in this transaction has left a check sitting in
        # the queue. This forces them to run now and empties it. Without it the
        # command dies with "cannot ALTER TABLE because it has pending trigger
        # events" -- on every deploy, not only under test.
        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        for table, trigger in IMMUTABLE_TRIGGERS:
            cur.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}")
        try:
            yield cur
        finally:
            for table, trigger in IMMUTABLE_TRIGGERS:
                cur.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}")


class Command(BaseCommand):
    help = "Seed categories, locations, items and eight weeks of movements."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Seed even if items already exist. Adds movements on top.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help=(
                "Delete previously seeded items and their history first, then "
                "seed again. Only touches the SKUs this command owns."
            ),
        )
        parser.add_argument(
            "--i-know-this-is-production",
            action="store_true",
            dest="allow_production",
            help="Required to use --reset when DEBUG is False.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()

        manager = User.objects.filter(role=User.Role.MANAGER).first()
        if manager is None:
            self.stderr.write("No manager found. Run create_demo_users first.")
            return

        if options["reset"]:
            self._reset(options)

        # "Has this seed already run?", not "is the database non-empty?".
        # Those differ the moment anything else lives in the table -- after a
        # --reset that spared real data, the old check saw the survivor and
        # skipped the reseed, so --reset deleted without restoring.
        already_seeded = Item.objects.filter(sku__in=SEEDED_SKUS).exists()
        if already_seeded and not options["force"]:
            self.stdout.write("Demo items already exist; nothing to do.")
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
        self._backdate_timeline(items)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(items)} items and "
                f"{StockMovement.objects.count()} movements."
            )
        )

    # ------------------------------------------------------------------

    def _reset(self, options):
        """Delete previously seeded data so the seed can run cleanly again.

        Two guards, because this deletes ledger rows with the immutability
        triggers switched off and there is no undo:

        1. It refuses to run with DEBUG=False unless explicitly overridden.
           Production is exactly where a mistake here is permanent.
        2. It only deletes the SKUs listed in this file. Deleting every item
           would take real data with it if this ever ran somewhere it should
           not -- and "somewhere it should not" is the entire scenario the
           first guard exists for.
        """
        if not settings.DEBUG and not options["allow_production"]:
            raise CommandError(
                "--reset deletes ledger rows and refuses to run with "
                "DEBUG=False. Pass --i-know-this-is-production if that is "
                "genuinely what you intend."
            )

        items = Item.objects.filter(sku__in=SEEDED_SKUS)
        item_ids = list(items.values_list("id", flat=True))
        if not item_ids:
            self.stdout.write("Nothing seeded to reset.")
            return

        with immutability_disabled():
            # Order matters: all three relations are PROTECT, so children have
            # to go before parents. Ledger entries reference movements, and
            # both reference items.
            LedgerEntry.objects.filter(item_id__in=item_ids).delete()
            StockMovement.objects.filter(item_id__in=item_ids).delete()
            ItemTimelineEvent.objects.filter(item_id__in=item_ids).delete()

        items.delete()
        self.stdout.write(f"Reset: removed {len(item_ids)} seeded item(s).")

    def _assign_staff(self, User, manager, locations):
        staff = User.objects.filter(role=User.Role.STAFF).order_by("id")
        if not staff.exists():
            return
        # First staff member: warehouse only. Second, if present: shop floor
        # and site store. Neither can act everywhere, which is the point --
        # an assignment covering everything demonstrates nothing.
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
        single spike."""
        now = timezone.now()
        warehouse = locations[0]
        # Movement ids in the order they were recorded. That order is the one
        # thing that must survive -- see the note below the loops.
        recorded = []

        # Opening stock, deliberately uneven so that some items finish below
        # their reorder level and the low-stock filter has something to find.
        for index, item in enumerate(items):
            if index % 8 == 0:
                opening = max(1, item.reorder_level // 3)  # will read as low
            elif index % 5 == 0:
                opening = item.reorder_level  # exactly at the level: lte, not lt
            else:
                opening = item.reorder_level * random.randint(3, 6)
            movement = ss.record_receipt(
                actor=manager,
                item=item,
                location=warehouse,
                quantity=opening,
                note="Opening stock",
            )
            recorded.append(movement.id)

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
                # database would then hold a state the app cannot produce.
                continue
            recorded.append(movement.id)

        # Timestamps are assigned in *recording* order, and every movement --
        # openings included -- goes through this single sorted assignment.
        #
        # stock_service validated each movement against the balance as it
        # stood at the moment it was recorded, so that sequence is causally
        # sound. Handing each movement an independent random date destroys
        # that: a transfer that put stock on the shop floor can end up dated
        # after the issue that removed it, and replaying the ledger
        # chronologically then shows a negative balance. The totals still come
        # out right -- sums do not care about order -- which is exactly why
        # this is easy to miss, and why a SUM(delta) >= 0 test passes while
        # the history says stock was issued from an empty shelf.
        #
        # Sorting the dates and zipping them onto the movements in order makes
        # chronological order identical to recording order. Putting the
        # openings through the same assignment, rather than pinning them to a
        # separate earlier range, is what keeps them first: they were recorded
        # first, so they take the earliest dates, with no constant that has to
        # be kept in step with the window.
        dates = sorted(
            now
            - timedelta(
                days=random.randint(0, HISTORY_DAYS),
                # Business hours, so the timestamps read like a working day
                # rather than a machine running at 3am.
                hours=random.randint(8, 17),
                minutes=random.randint(0, 59),
            )
            for _ in recorded
        )
        self._backdate(list(zip(recorded, dates)))

    def _backdate(self, schedule):
        """Apply (movement_id, timestamp) pairs.

        recorded_at is auto_now_add, so it cannot be set through the service.
        Both the movement and its ledger entries move together -- occurred_at
        is what every date-range report reads, so leaving it behind would make
        the ledger and the movement list disagree.
        """
        if not schedule:
            return

        with immutability_disabled() as cur:
            for movement_id, when in schedule:
                cur.execute(
                    "UPDATE stock_movement SET recorded_at = %s WHERE id = %s",
                    [when, movement_id],
                )
                cur.execute(
                    "UPDATE stock_ledger_entry SET occurred_at = %s "
                    "WHERE movement_id = %s",
                    [when, movement_id],
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

    def _backdate_timeline(self, items):
        """Give the item history the same treatment as the ledger.

        Timeline events are auto_now_add too, so without this an item reads as
        created today while its movements run back two months -- created after
        its own history. Goal 9's page is the one asserting that this record
        can be trusted, and an impossible creation date undercuts that at a
        glance, before anyone reads a word of it.

        Item.created_at moves as well, or the item header and its timeline
        disagree about the same fact.
        """
        with immutability_disabled() as cur:
            for item in items:
                first_movement = (
                    StockMovement.objects.filter(item=item)
                    .order_by("recorded_at")
                    .values_list("recorded_at", flat=True)
                    .first()
                )
                if first_movement is None:
                    continue

                # The item has to exist before anything can move through it.
                created_at = first_movement - timedelta(days=1, hours=2)
                cur.execute(
                    "UPDATE catalog_item SET created_at = %s WHERE id = %s",
                    [created_at, item.id],
                )

                # Ordered by id, which is the order they were written. The
                # CREATED event sits with the item; everything after it --
                # field changes, notes, archiving -- is spread across the
                # window so the timeline reads as activity over time rather
                # than one burst on a single afternoon.
                event_ids = list(
                    ItemTimelineEvent.objects.filter(item=item)
                    .order_by("id")
                    .values_list("id", flat=True)
                )
                if not event_ids:
                    continue

                span = (timezone.now() - first_movement) / len(event_ids)
                for position, event_id in enumerate(event_ids):
                    when = (
                        created_at
                        if position == 0
                        else first_movement + span * position
                    )
                    cur.execute(
                        "UPDATE catalog_item_timeline_event "
                        "SET created_at = %s WHERE id = %s",
                        [when, event_id],
                    )
