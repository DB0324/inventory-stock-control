"""The catalogue: what we stock, and how it is grouped.

Plain CRUD tables. Nothing in here knows anything about quantities -- see the
note on Item below, that omission is the whole point.
"""

from django.db import models
from django.db.models.functions import Upper
from django.conf import settings
from apps.stock.models import ImmutableModel

class Category(models.Model):
    """A maintained list, not free text typed per item (goal 2).

    Free-text categories drift into "Fasteners", "fasteners" and "Fastners"
    within a week, and then no report can be trusted.
    """

    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_category"
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Item(models.Model):
    """A stocked product.

    Note what is absent: any quantity field. On-hand is always derived by
    summing ledger entries (goal 4). A column here would be a second source
    of truth, and that drift is exactly what this system exists to prevent.
    """

    sku = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    unit_of_measure = models.CharField(max_length=16, default="EA")
    reorder_level = models.IntegerField(default=0)
    # PROTECT: deleting a category out from under live items would orphan
    # them. Categories get is_active=False instead.
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="items",
    )
    is_archived = models.BooleanField(
        default=False,
        help_text=(
            "Archived items drop out of day-to-day lists and reject new "
            "movements, but keep their full history."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_item"
        ordering = ["name"]
        constraints = [
            # Same functional-index pattern as User.email, one case flipped:
            # SKUs are uppercased because that is how people write them and
            # how they appear on labels. 'a-100' and 'A-100' are one SKU, and
            # the database is what says so.
            models.UniqueConstraint(
                Upper("sku"),
                name="item_sku_ci_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(reorder_level__gte=0),
                name="item_reorder_level_non_negative",
            ),
        ]


    def __str__(self):
        return f"{self.sku} - {self.name}"

    def save(self, *args, **kwargs):
        # Normalise on the way in so the stored value matches the constraint's
        # view of it. The constraint stops bad data; this stops surprises.
        self.sku = self.sku.upper()
        return super().save(*args, **kwargs)


class ItemTimelineEvent(ImmutableModel):
    """Goal 9: an item's history, which nobody can edit -- including managers.

    Field changes and notes live in one table because the requirement says
    notes are part of the same timeline. Two tables merged in a template would
    render the same thing but break the moment you paginate.

    old_value and new_value are text, not foreign keys. If a category is
    renamed later, this entry must still show what the value was at the time.
    A FK would rewrite history retroactively, which is what goal 9 forbids.
    """

    class EventType(models.TextChoices):
        CREATED = "CREATED", "Created"
        FIELD_CHANGE = "FIELD_CHANGE", "Field changed"
        NOTE = "NOTE", "Note"
        ARCHIVED = "ARCHIVED", "Archived"
        RESTORED = "RESTORED", "Restored"

    item = models.ForeignKey(
        Item, on_delete=models.PROTECT, related_name="timeline", db_index=False,
    )
    event_type = models.CharField(max_length=16, choices=EventType.choices)
    field_name = models.CharField(max_length=50, null=True, blank=True)
    old_value = models.TextField(null=True, blank=True)
    new_value = models.TextField(null=True, blank=True)
    note_body = models.TextField(null=True, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="timeline_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_item_timeline_event"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(event_type="FIELD_CHANGE", field_name__isnull=False,
                             note_body__isnull=True)
                    | models.Q(event_type="NOTE", note_body__isnull=False,
                               field_name__isnull=True)
                    | models.Q(event_type__in=["CREATED", "ARCHIVED", "RESTORED"])
                ),
                name="timeline_event_shape_valid",
            ),
        ]
        indexes = [
            models.Index(fields=["item", "-created_at"], name="timeline_item_time_idx"),
        ]

    def __str__(self):
        return f"{self.event_type} on item {self.item_id}"