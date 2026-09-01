"""Settings shared by every environment.

Nothing in this file may differ between development and production. Anything
that does belongs in dev.py or prod.py -- see ADR-007, where the cross-origin
cookie settings are the reason this split exists.
"""

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
    # apps.accounts, apps.catalog, apps.stock -- added in Phase 1
    "apps.accounts",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "accounts.User"

SILENCED_SYSTEM_CHECKS = ["auth.E003"]


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

import sys

_SCHEMA_COMMANDS = {"migrate", "makemigrations", "sqlmigrate", "dbshell", "flush"}
_needs_direct = any(cmd in sys.argv for cmd in _SCHEMA_COMMANDS)

_db_url = env("DATABASE_URL_DIRECT", default="") if _needs_direct else ""
_db_url = _db_url or env("DATABASE_URL")

DATABASES = {"default": env.db_url_config(_db_url)}

DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=0)
DATABASES["default"]["OPTIONS"] = {"sslmode": env("PGSSLMODE", default="require")}
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

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
