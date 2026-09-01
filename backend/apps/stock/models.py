"""Where stock physically sits, and who is allowed to touch it.

Location lives here rather than in catalog because the ledger references it
on every single row. catalog is the "what", stock is the "where and when" --
and the "what" should not need to import the "where".
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
