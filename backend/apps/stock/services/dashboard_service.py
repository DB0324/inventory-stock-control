"""Dashboard aggregates (goal 8).

Every number here is a SQL aggregate over the ledger. None of it is cached or
stored, for the same reason no item carries an on_hand column: a second copy
of a derived number is a second thing that can be wrong.

The date boundaries are the subtle part. "Today" and "this week" are business
questions, so they are answered in the configured business timezone, not in
UTC. An evening movement in Asia/Kolkata is already tomorrow in UTC, and a
dashboard that quietly filed it under the wrong day would be wrong at exactly
the time of day people check it.
"""

from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce, TruncWeek
from django.utils import timezone

from apps.catalog.models import Item
from apps.stock.models import LedgerEntry, StockMovement
from apps.stock.services import alert_service

CHART_WEEKS = 8


def _local_day_start(when=None):
    """Midnight in the business timezone, as an aware datetime."""
    local = timezone.localtime(when or timezone.now())
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def _local_week_start(when=None):
    """Monday of the current week, in the business timezone.

    ISO weeks rather than a rolling seven days: "this week" to the person
    reading a dashboard on Monday morning means a nearly empty week, not the
    last seven days of a week that already ended.
    """
    day = _local_day_start(when)
    return day - timedelta(days=day.weekday())


def headline_numbers():
    today = _local_day_start()
    week = _local_week_start()

    return {
        "active_items": Item.objects.filter(is_archived=False).count(),
        # Reuses the alerts query, so the dashboard tile and the alerts page
        # can never disagree -- including about dismissals.
        "low_stock_items": alert_service.alert_count(),
        "movements_today": StockMovement.objects.filter(
            recorded_at__gte=today
        ).count(),
        # Distinct *items*, not movements: ten receipts of the same bolt is
        # one item moving, and the brief asks how much of the catalogue is
        # active this week.
        "items_moved_this_week": StockMovement.objects.filter(
            recorded_at__gte=week
        )
        .values("item_id")
        .distinct()
        .count(),
        "week_starts": week.date().isoformat(),
    }


def on_hand_by_category():
    """Stock split by category, zero-filled.

    A category with nothing in it is a real answer -- arguably the more
    interesting one -- so this counts from Item outward rather than from the
    ledger, which would only ever return categories that have stock.
    """
    rows = (
        Item.objects.filter(is_archived=False)
        .values("category__name")
        .annotate(on_hand=Coalesce(Sum("ledger_entries__delta"), 0))
        .order_by("category__name")
    )
    return [
        {"label": row["category__name"], "on_hand": row["on_hand"]} for row in rows
    ]


def on_hand_by_location():
    from apps.stock.models import Location

    rows = (
        Location.objects.filter(is_active=True)
        .values("code", "name")
        .annotate(on_hand=Coalesce(Sum("ledger_entries__delta"), 0))
        .order_by("code")
    )
    return [
        {"label": row["code"], "name": row["name"], "on_hand": row["on_hand"]}
        for row in rows
    ]


def movement_volume_by_week(weeks=CHART_WEEKS):
    """Receipt and issue volume per week, oldest first.

    Weeks with no activity are filled in rather than skipped. A chart that
    silently drops empty weeks compresses a quiet fortnight into a single gap
    and makes the trend look steadier than it was.

    Adjustments and transfers are excluded on purpose: a transfer moves stock
    without changing the total, and an adjustment is a correction rather than
    trade. Counting either would make the two lines stop meaning "stock in"
    and "stock out".
    """
    start = _local_week_start() - timedelta(weeks=weeks - 1)

    rows = (
        StockMovement.objects.filter(recorded_at__gte=start)
        .annotate(week=TruncWeek("recorded_at"))
        .values("week")
        .annotate(
            receipts=Coalesce(Sum("quantity", filter=Q(kind="RECEIPT")), 0),
            issues=Coalesce(Sum("quantity", filter=Q(kind="ISSUE")), 0),
            movements=Count("id"),
        )
        .order_by("week")
    )
    by_week = {
        timezone.localtime(row["week"]).date(): row for row in rows if row["week"]
    }

    series = []
    for offset in range(weeks):
        week_start = (start + timedelta(weeks=offset)).date()
        row = by_week.get(week_start)
        series.append(
            {
                "week": week_start.isoformat(),
                "receipts": row["receipts"] if row else 0,
                "issues": row["issues"] if row else 0,
                "movements": row["movements"] if row else 0,
            }
        )
    return series


def recent_movements(limit=8):
    """The newest few, so the dashboard shows activity and not only totals."""
    return StockMovement.objects.select_related(
        "item", "recorded_by", "location", "source_location", "destination_location"
    )[:limit]


def total_on_hand():
    return LedgerEntry.objects.aggregate(
        total=Coalesce(Sum("delta"), 0)
    )["total"]
