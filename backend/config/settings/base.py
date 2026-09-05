"""Settings shared by every environment.

Nothing in this file may differ between development and production. Anything
that does belongs in dev.py or prod.py -- see ADR-007, where the cross-origin
cookie settings are the reason this split exists.
"""

import sys
from pathlib import Path

import environ

# This file is backend/config/settings/base.py, so parents[2] is backend/.
BASE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BASE_DIR.parent

env = environ.Env()
environ.Env.read_env(REPO_ROOT / ".env")

# No default. A missing SECRET_KEY must stop the process, not fall back to a
# known value that would boot successfully in production.
SECRET_KEY = env("SECRET_KEY")

# --- Applications --------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "corsheaders",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.catalog",
    "apps.stock",
    "apps.api",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "accounts.User"

SILENCED_SYSTEM_CHECKS = ["auth.E003"]

# --- DRF -----------------------------------------------------------------
# Session auth, not tokens (ADR-007). The cookie is HttpOnly, so an XSS bug
# cannot read it, and logout revokes server-side immediately.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "apps.api.exception_handler.handler",
    "DEFAULT_THROTTLE_RATES": {
        # The per-account limit does the real work: five failures a minute
        # against one email, which makes a password list useless while
        # leaving room for someone who has forgotten which password they
        # used.
        #
        # The per-address limit is deliberately looser, because it is the one
        # that can be wrong. Getting the client address right behind two
        # proxies depends on NUM_PROXIES below being correct for the
        # deployment; if it is not, every request looks like it comes from
        # the proxy and a tight limit would lock out all users at once. A
        # loose limit degrades to "no per-IP protection" rather than to an
        # outage, and the email limit is unaffected either way since it keys
        # on the request body rather than on any header.
        "login_ip": "30/min",
        "login_email": "5/min",
    },
    # NUM_PROXIES tells DRF how many proxies sit in front of this app, so it
    # reads the client address from the right position in X-Forwarded-For.
    # Left unset, DRF trusts the leftmost value -- which the client sends and
    # can therefore forge, making the per-IP limit trivially bypassable by
    # varying one header. Vercel proxies /api to Render and Render has its own
    # load balancer, so 2 is the expectation; it is an env var because that
    # count is a property of the deployment, not of the code, and the only way
    # to be sure of it is to look at a real X-Forwarded-For in the logs.
    "NUM_PROXIES": env.int("NUM_PROXIES", default=2),
}

# DRF returns 403 for unauthenticated requests when SessionAuthentication is
# the only backend, because it has no WWW-Authenticate header to send. An SPA
# needs to tell "log in" apart from "you may not do that", so we force 401.
REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] = [
    "apps.api.authentication.CsrfSessionAuthentication",
]

MIDDLEWARE = [
    # CorsMiddleware must precede CommonMiddleware so preflight responses
    # carry the CORS headers before any redirect can occur.
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Last, so it runs on the way out after every other middleware has had its
    # say and cannot have its headers overwritten by one of them.
    "apps.api.middleware.ApiCacheControlMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# --- Database ------------------------------------------------------------
# Neon's pooled endpoint (hostname contains "-pooler") runs PgBouncer in
# transaction-pooling mode. Two consequences:
#
#   1. Schema commands issue session-level SET statements that do not survive
#      transaction pooling, so they use the direct endpoint instead.
#   2. Server-side cursors do not survive it either, and Django's .iterator()
#      uses them -- which the Phase 6 CSV export will want.
#
# ADR-002's advisory locks are unaffected: pg_advisory_xact_lock lives and
# dies inside one transaction, which PgBouncer pins to a single backend.
# The session-scoped variant would break here -- a second, independent reason
# for the _xact_ choice.

_SCHEMA_COMMANDS = {"migrate", "makemigrations", "sqlmigrate", "dbshell", "flush"}
_needs_direct = any(cmd in sys.argv for cmd in _SCHEMA_COMMANDS)

_db_url = env("DATABASE_URL_DIRECT", default="") if _needs_direct else ""
_db_url = _db_url or env("DATABASE_URL")

DATABASES = {"default": env.db_url_config(_db_url)}

DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=0)
DATABASES["default"]["OPTIONS"] = {"sslmode": env("PGSSLMODE", default="require")}
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

# --- Cache ---------------------------------------------------------------
# The database, not local memory. The cache backs the login rate limiter, and
# LocMemCache is per-process: with several gunicorn workers each one would
# keep its own counter, so "five attempts" would silently become five per
# worker. A shared cache is the difference between a rate limit and the
# appearance of one.
#
# Redis would be the usual answer and is a drop-in replacement here, but it is
# another service to run. Postgres is already there, already shared by every
# worker, and the traffic this cache sees is tiny -- a few rows per login
# attempt. The table is created by `manage.py createcachetable`, which
# build.sh runs on every deploy.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_table",
    }
}

# --- Sessions and cookies ------------------------------------------------
# Two weeks, refreshed on every request. Without SESSION_SAVE_EVERY_REQUEST
# the expiry is absolute: someone using the system daily would still be
# thrown out mid-task a fortnight after signing in. With it, the clock resets
# while they are working and only runs down once they stop.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_SAVE_EVERY_REQUEST = True

# Defence in depth rather than the main protection. The session cookie is
# HttpOnly so script cannot read it at all; these stop it being sent along
# with a cross-site request in the first place. prod.py raises both to
# None/Secure only if the deployment is genuinely cross-origin -- ours is not
# any more, because Vercel proxies /api (ADR-007).
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# --- Internationalisation ------------------------------------------------
# USE_TZ stores timestamptz in UTC and converts on the way out; TIME_ZONE is
# the business day boundary used for the dashboard's "today" and "this week"
# (goal 8). Getting this pair wrong puts an evening movement in yesterday.

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="Asia/Kolkata")
USE_I18N = True
USE_TZ = True

# --- Static files --------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
