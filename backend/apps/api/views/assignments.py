"""Who may record movements where (goal 5).

Manager-only throughout. Reading the list tells you exactly which staff can
act at which locations, which is itself sensitive -- and only a manager can
change it, so there is nobody else with a reason to look.
"""

from django.contrib.auth import get_user_model
from rest_framework import mixins, viewsets

from apps.api.permissions import IsManager
from apps.api.serializers import AssignmentSerializer, StaffSerializer
from apps.stock.models import LocationAssignment


class StaffViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Staff accounts and their current assignments.

    Read-only: creating users is out of scope for this screen, and deleting
    one would orphan the movements they recorded -- which PROTECT forbids
    anyway.
    """

    permission_classes = [IsManager]
    serializer_class = StaffSerializer

    def get_queryset(self):
        User = get_user_model()
        return (
            User.objects.filter(role=User.Role.STAFF)
            # Without prefetch this is one extra query per staff member, and
            # the screen exists precisely to show every one of them at once.
            .prefetch_related("location_assignments__location")
            .order_by("full_name", "id")
        )


class AssignmentViewSet(
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Grant and revoke. No update route: changing which user or location an
    existing grant points at is not an edit, it is a different grant, and
    modelling it as one would blur who was given what and when."""

    permission_classes = [IsManager]
    serializer_class = AssignmentSerializer
    queryset = LocationAssignment.objects.select_related(
        "user", "location", "assigned_by"
    )

    def perform_create(self, serializer):
        # The grantor is the person making the request, never a field the
        # client can set. A forgeable audit trail is worse than none, because
        # it looks trustworthy.
        serializer.save(assigned_by=self.request.user)
