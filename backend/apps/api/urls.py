from django.urls import path

from apps.api.views import auth

urlpatterns = [
    path("auth/csrf/", auth.csrf, name="csrf"),
    path("auth/login/", auth.login_view, name="login"),
    path("auth/logout/", auth.logout_view, name="logout"),
    path("auth/me/", auth.me, name="me"),
]