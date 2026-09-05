"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import logging

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


logger = logging.getLogger(__name__)


def healthz(request):
    """Liveness check. Touches the database, because a process that is up
    but cannot reach Postgres is not healthy in any useful sense.

    The failure body says nothing. psycopg's connection errors quote the
    host, port, user and database name back at you -- "connection to server at
    ep-xxxx.eu-central-1.aws.neon.tech (1.2.3.4), port 5432 failed: password
    authentication failed for user ..." -- and this endpoint is public and
    unauthenticated, so anyone can ask. An attacker who can make the database
    briefly unreachable, or who simply catches a cold start, would be handed
    the infrastructure layout for free.

    The detail still exists; it goes to the application log, where the
    operator can read it and the internet cannot.
    """
    from django.db import connection
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except Exception:
        logger.exception("Health check failed: the database is unreachable")
        return JsonResponse({"status": "error"}, status=503)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.api.urls")),
    path("healthz/", healthz),
]
