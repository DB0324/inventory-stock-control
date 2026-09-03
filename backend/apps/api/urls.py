from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.api.views import auth, catalog, locations, movements

router = DefaultRouter()
router.register("categories", catalog.CategoryViewSet, basename="category")
router.register("items", catalog.ItemViewSet, basename="item")
router.register("locations", locations.LocationViewSet, basename="location")

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

    path("", include(router.urls)),
]