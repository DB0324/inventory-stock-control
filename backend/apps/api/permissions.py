from rest_framework.permissions import BasePermission


class IsManager(BasePermission):
    """Manager-only endpoints: items, categories, locations, assignments,
    adjustments, alert dismissal.

    Staff receive 403 here, not a hidden button. Goal 1 says the difference
    must be enforced on the server, so this is what the tests hit directly.
    """

    message = "This action requires the inventory manager role."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.is_manager)


class CanRecordMovement(BasePermission):
    """Both roles may record movements. Which *locations* they may record at
    is checked in the service layer, because that rule has to hold for CSV
    import and the seed command too, not just for HTTP requests.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)