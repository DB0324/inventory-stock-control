from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """Application user.

    Two roles, held as a column rather than Django Groups. The semantics are
    fixed by the brief and never user-configurable, so a column is explicit,
    greppable, and joinable. Groups would be right if roles were data.

    Managers hold no LocationAssignment rows (Phase 3). Their access is
    universal by role, so that deleting an assignment row can never silently
    revoke a manager's reach.
    """

    class Role(models.TextChoices):
        MANAGER = "MANAGER", "Inventory manager"
        STAFF = "STAFF", "Warehouse staff"

    email = models.EmailField(max_length=254)
    full_name = models.CharField(max_length=150)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.STAFF)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(
        default=False,
        help_text="Django admin access. Unrelated to the STAFF role above.",
    )
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        db_table = "accounts_user"
        constraints = [
            # Case-insensitive uniqueness via a functional index. Django
            # removed CIEmailField in 5.1, and citext is discouraged upstream;
            # a Lower() constraint is the current idiom and needs no extension.
            models.UniqueConstraint(Lower("email"), name="user_email_ci_unique"),
            models.CheckConstraint(
                condition=models.Q(role__in=["MANAGER", "STAFF"]),
                name="user_role_valid",
            ),
        ]
        indexes = [models.Index(fields=["role"], name="user_role_idx")]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        return super().save(*args, **kwargs)

    @property
    def is_manager(self) -> bool:
        return self.role == self.Role.MANAGER