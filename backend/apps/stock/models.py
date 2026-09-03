"""Where stock physically sits, who may touch it, and the append-only history.

Location lives here rather than in catalog because the ledger references it
on every single row. catalog is the "what", stock is the "where and when" --
and the "what" should not need to import the "where".

The bottom half of this file is ADR-001: StockMovement is the *event* (what a
person did) and LedgerEntry is the *effect* (what it did to one shelf). Keeping
them apart is what lets a transfer be one honest event with two balance effects
instead of two half-events that could drift apart.
"""

from django.conf import settings
from django.db import models


class Location(models.Model):
    """A physical place stock can sit: warehouse, shop floor, project site."""

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(
        default=True,
        help_text=(
            "Locations are deactivated, never deleted. Ledger entries "
            "reference them with PROTECT, so a delete would fail anyway."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_location"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class LocationAssignment(models.Model):
    """Which staff may record movements where.

    An explicit through-table rather than a ManyToManyField on User, because
    it carries assigned_by and assigned_at -- we want to be able to answer
    "who gave this person access, and when" during an audit.

    Managers hold no rows here. Their access is universal by role, so that
    deleting a row can never silently revoke a manager's reach.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="location_assignments",
    )
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    # PROTECT, not CASCADE: losing the grantor must never quietly erase the
    # record of the grant. Deactivate the user instead of deleting them.
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assignments_made",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_location_assignment"
        constraints = [
            # At the database, not in a form. Two managers assigning the same
            # person at the same moment is a race a form check cannot win.
            models.UniqueConstraint(
                fields=["user", "location"],
                name="location_assignment_unique",
            ),
        ]
        indexes = [
            # Every permission check is "which locations does this user have?",
            # so the user column is the one that needs the index.
            models.Index(fields=["user"], name="assignment_user_idx"),
        ]

    def __str__(self):
        return f"{self.user.email} @ {self.location.code}"


class ImmutabilityError(Exception):
    """Raised on any attempt to mutate an append-only row."""


class ImmutableModel(models.Model):
    """Append-only. Rows may be created, never changed or removed.

    This is the second of three layers. The first is that no update or delete
    code path exists anywhere in the app; the third is a database trigger.
    Only the trigger is a real guarantee -- Model.save() is not even consulted
    by queryset.update() or a bulk delete, so this class catches the honest
    mistakes and the trigger catches everything else.
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # A row that already has a pk has already been written once. There is
        # no legitimate second save.
        if self.pk is not None:
            raise ImmutabilityError(f"{type(self).__name__} rows are append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutabilityError(f"{type(self).__name__} rows cannot be deleted.")


class MovementKind(models.TextChoices):
    RECEIPT = "RECEIPT", "Receipt"
    ISSUE = "ISSUE", "Issue"
    TRANSFER = "TRANSFER", "Transfer"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"


class StockMovement(ImmutableModel):
    """The business event: what a person did.

    Balance effects live in LedgerEntry (ADR-001). A transfer is one movement
    with two entries; everything else is one movement with one entry.

    quantity is always the magnitude as entered, never signed. A user typing
    "issue 5" means five, not minus five. The sign is decided in exactly one
    place -- the service layer, when it writes the entries -- so there is only
    ever one line of code that can get it wrong.
    """

    item = models.ForeignKey(
        "catalog.Item", on_delete=models.PROTECT, related_name="movements"
    )
    kind = models.CharField(max_length=16, choices=MovementKind.choices)
    quantity = models.IntegerField()

    # Three location columns instead of one, because a transfer genuinely has
    # two ends. Squeezing it into a single column would mean either two half
    # movements that can drift apart, or one nullable "other end" that means
    # something different for every kind. The CHECK below is what keeps three
    # columns from turning into a mess.
    #
    # location: set for RECEIPT, ISSUE, ADJUSTMENT. Null for TRANSFER.
    location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movements",
    )
    # source/destination: set for TRANSFER only.
    source_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movements_out",
    )
    destination_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movements_in",
    )

    # Nullable rather than blank="": the CHECK below has to tell "no reason
    # was given" apart from "a reason does not apply to this kind", and NULL
    # says that more honestly than an empty string.
    reason = models.TextField(null=True, blank=True)
    note = models.TextField(blank=True, default="")

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="movements_recorded",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_movement"
        # Newest first, with id as the tie-break. Two movements recorded in
        # the same millisecond would otherwise come back in arbitrary order
        # and paginate inconsistently -- page 2 could repeat a row from page 1.
        ordering = ["-recorded_at", "-id"]
        constraints = [
            # Shape. A malformed row here would corrupt every aggregate in the
            # system, so the database refuses it no matter who is writing --
            # the API, a shell session, or a future me at 2am.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind="TRANSFER",
                        location__isnull=True,
                        source_location__isnull=False,
                        destination_location__isnull=False,
                    )
                    # A transfer to the same shelf is a no-op that would still
                    # write two cancelling ledger rows. Not worth allowing.
                    & ~models.Q(source_location=models.F("destination_location"))
                )
                | (
                    ~models.Q(kind="TRANSFER")
                    & models.Q(
                        location__isnull=False,
                        source_location__isnull=True,
                        destination_location__isnull=True,
                    )
                ),
                name="movement_shape_valid",
            ),
            # Goal 4: "every adjustment must carry a reason". The regex is
            # there because "   " is not a reason, and a NOT NULL test on its
            # own would happily accept it.
            models.CheckConstraint(
                condition=~models.Q(kind="ADJUSTMENT")
                | (models.Q(reason__isnull=False) & ~models.Q(reason__regex=r"^\s*$")),
                name="movement_adjustment_needs_reason",
            ),
            models.CheckConstraint(
                condition=~models.Q(quantity=0),
                name="movement_quantity_non_zero",
            ),
        ]
        indexes = [
            # "History for this item, newest first" -- the item detail page.
            models.Index(
                fields=["item", "-recorded_at"], name="movement_item_time_idx"
            ),
            # "Recent activity across everything" -- the dashboard.
            models.Index(fields=["-recorded_at"], name="movement_time_idx"),
        ]

    def __str__(self):
        return f"{self.kind} {self.quantity} of item {self.item_id}"


class LedgerEntry(ImmutableModel):
    """The balance effect: what a movement did to one shelf.

    Every quantity question in the system reduces to this one query:

        SELECT COALESCE(SUM(delta), 0) FROM stock_ledger_entry
        WHERE item_id = ? [AND location_id = ?]

    item_id and occurred_at are copied down from the movement rather than
    joined for. That is denormalisation, which I would normally argue against,
    but both facts are frozen the instant they are written, so there is no
    such thing as them going stale -- and it lets the index below answer a
    balance query without ever opening stock_movement.
    """

    movement = models.ForeignKey(
        StockMovement, on_delete=models.PROTECT, related_name="entries"
    )
    item = models.ForeignKey(
        "catalog.Item", on_delete=models.PROTECT, related_name="ledger_entries"
    )
    location = models.ForeignKey(
        Location, on_delete=models.PROTECT, related_name="ledger_entries"
    )
    delta = models.IntegerField(help_text="Signed. Negative removes stock.")
    occurred_at = models.DateTimeField()

    class Meta:
        db_table = "stock_ledger_entry"
        constraints = [
            # A zero delta is a row that says nothing and still costs a read.
            models.CheckConstraint(
                condition=~models.Q(delta=0),
                name="ledger_delta_non_zero",
            ),
        ]
        indexes = [
            # The on-hand query, exactly.
            models.Index(fields=["item", "location"], name="ledger_item_location_idx"),
            # Date-range reporting (goal 8).
            models.Index(fields=["occurred_at"], name="ledger_occurred_idx"),
        ]

    def __str__(self):
        return f"item {self.item_id} @ location {self.location_id}: {self.delta:+d}"


class LowStockDismissal(models.Model):
    """A manager saying "yes, I know" about one item's low-stock alert.

    Deliberately NOT append-only, unlike everything else in this file. The
    ledger is a record of what happened and must never change; this is
    operational state about what someone wants to see on a screen. Making it
    immutable would mean writing a second row to undo the first and then
    reasoning about which one wins, which is more machinery than the problem
    deserves.

    The requirement is that a dismissed alert comes back if the item rises
    above its reorder level and then falls to or below it again. Two fields
    carry that:

    * cleared_at -- set the moment a movement takes the item back above its
      reorder level. stock_service calls into here on every write, so this
      costs one comparison per movement rather than a replay of the ledger.
      The alternative was deriving "did it ever recover?" by walking every
      entry since the dismissal, which is correct but pays for history the
      system already knows how to summarise.

    * reorder_level -- the threshold as it stood when the alert was
      dismissed. If a manager later raises the reorder level, the item is low
      against a bar nobody has acknowledged, so the dismissal no longer
      applies and the alert returns.
    """

    item = models.ForeignKey(
        "catalog.Item",
        on_delete=models.PROTECT,
        related_name="low_stock_dismissals",
    )
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="alerts_dismissed",
    )
    dismissed_at = models.DateTimeField(auto_now_add=True)
    reorder_level = models.IntegerField(
        help_text="The threshold at the time of dismissal, not the item's current one.",
    )
    cleared_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when stock recovered above the reorder level.",
    )

    class Meta:
        db_table = "stock_low_stock_dismissal"
        ordering = ["-dismissed_at"]
        constraints = [
            # At most one live dismissal per item, enforced by a partial
            # index. Cleared rows stay for the audit trail, so a plain unique
            # constraint would block the second dismissal after a recovery.
            models.UniqueConstraint(
                fields=["item"],
                condition=models.Q(cleared_at__isnull=True),
                name="one_active_dismissal_per_item",
            ),
        ]
        indexes = [
            models.Index(
                fields=["item"],
                condition=models.Q(cleared_at__isnull=True),
                name="active_dismissal_idx",
            ),
        ]

    def __str__(self):
        state = "cleared" if self.cleared_at else "active"
        return f"dismissal for item {self.item_id} ({state})"
