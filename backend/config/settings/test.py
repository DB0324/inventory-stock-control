"""Tests run against a local Postgres, not Neon.

Same major version, so every guarantee Phase 0 verified on the real host
holds here too. The point is latency: a suite that takes 90 seconds is a
suite you stop running.
"""

from .dev import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "inventory",
        "USER": "inventory",
        "PASSWORD": "inventory",
        "HOST": "localhost",
        "PORT": "5432",
        "CONN_MAX_AGE": 0,
        "OPTIONS": {},
        "DISABLE_SERVER_SIDE_CURSORS": True,
    }
}

# Fast hashing. Irrelevant to correctness, meaningful to runtime.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]