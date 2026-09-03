"""Settings for the test suite. Points at the local container, never at Neon.

Tests are destructive by nature -- pytest-django creates and drops a database,
and `--create-db` will do it without asking. So the important thing in this
file is not the connection settings, it is the guard at the bottom that makes
pointing the suite at a real database an error rather than an accident.

The database itself is docker-compose.yml's `db` service: Postgres 17, the
same major version as Neon, so triggers, advisory locks, pg_trgm and partial
indexes all behave the way Phase 0 verified them on the real host.
"""

from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import env

# Inherits from base, not dev. Tests should not run with DEBUG=True -- it
# changes error handling and hides the 500s a test ought to catch. The cost is
# that dev's ALLOWED_HOSTS does not come along, so it is spelled out here.
# Django's test setup appends "testserver" itself, but relying on that is the
# kind of implicit dependency that breaks confusingly two releases later.
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

# Faster than the real hashers by roughly an order of magnitude. Test users
# are created constantly and nothing here is protecting a real password.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# The default matches docker-compose.yml exactly, so `pytest` works with no
# environment set up at all -- one less thing to get wrong on a fresh clone.
TEST_DATABASE_URL = env(
    "TEST_DATABASE_URL",
    default="postgres://inventory:inventory@localhost:5432/inventory",
)

DATABASES = {"default": env.db_url_config(TEST_DATABASE_URL)}

# The container speaks plain TCP. base.py defaults sslmode to "require" for
# Neon, which would refuse to connect here.
DATABASES["default"]["OPTIONS"] = {"sslmode": "disable"}
DATABASES["default"]["CONN_MAX_AGE"] = 0
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True


# --- The guard -----------------------------------------------------------
# An allowlist, not a blocklist. Blocking "neon.tech" would feel safer than it
# is: it would happily let the suite drop a staging database on some other
# host. Naming the hosts we *do* accept fails closed instead.

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "db"}

_host = (urlparse(TEST_DATABASE_URL).hostname or "").lower()

if _host not in _LOCAL_HOSTS and not env.bool("ALLOW_REMOTE_TEST_DB", default=False):
    raise ImproperlyConfigured(
        f"Refusing to run tests against non-local host {_host!r}. "
        f"The suite creates and drops databases. If this really is a "
        f"throwaway host, set ALLOW_REMOTE_TEST_DB=1 to override."
    )

# WhiteNoise warns about a missing staticfiles/ on every request. The
# directory is created by collectstatic at deploy time and tests never serve
# static files, so use Django's plain storage here instead.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}