from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.api.views import (
    accounts, alerts, assignments, auth, catalog, dashboard, imports,
    locations, movements,
)

router = DefaultRouter()
router.register("categories", catalog.CategoryViewSet, basename="category")
router.register("items", catalog.ItemViewSet, basename="item")
router.register("locations", locations.LocationViewSet, basename="location")
# Goal 5. Manager-only, both of them.
router.register("staff", assignments.StaffViewSet, basename="staff")
# Who has an account at all, as opposed to who may act where. Manager-only,
# and separate from "staff" because that list excludes managers by design.
router.register("accounts", accounts.AccountViewSet, basename="account")
router.register("assignments", assignments.AssignmentViewSet, basename="assignment")

urlpatterns = [
    path("auth/csrf/", auth.csrf, name="csrf"),
    path("auth/login/", auth.login_view, name="login"),
    path("auth/logout/", auth.logout_view, name="logout"),
    path("auth/me/", auth.me, name="me"),

    # Four routes, not one polymorphic endpoint. Note there is no PUT, PATCH
    # or DELETE anywhere near a movement -- that absence is the point.
    path("movements/receipt/", movements.receipt, name="receipt"),
    path("movements/issue/", movements.issue, name="issue"),
    path("movements/adjustment/", movements.adjustment, name="adjustment"),
    path("movements/transfer/", movements.transfer, name="transfer"),

    # Goal 10. The count is its own endpoint so the navigation badge does not
    # pay for a serialized page of items on every screen that displays it.
    path("dashboard/", dashboard.dashboard, name="dashboard"),

    # Goal 7. Manager-only: bulk writes are still writes.
    path("imports/items/", imports.import_items, name="import-items"),
    path("imports/receipts/", imports.import_receipts, name="import-receipts"),
    path("exports/stock-position/", imports.export_stock_position,
         name="export-stock-position"),

    path("alerts/", alerts.list_alerts, name="alerts"),
    path("alerts/count/", alerts.alert_count, name="alert-count"),
    path("alerts/<int:item_id>/dismiss/", alerts.dismiss_alert, name="dismiss-alert"),

    path("", include(router.urls)),
]