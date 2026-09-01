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
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

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
# One connection string, 12-factor style. Neon and Render both speak this.

DATABASES = {"default": env.db_url("DATABASE_URL")}

# CONN_MAX_AGE=0 by default: Neon's pooled endpoint already pools connections,
# and Django holding persistent connections behind a scale-to-zero database
# yields stale-connection errors after idle periods.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=0)
DATABASES["default"]["OPTIONS"] = {"sslmode": env("PGSSLMODE", default="require")}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

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
