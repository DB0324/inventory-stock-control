"""Rate limiting for the login endpoint.

Two throttles, because a login endpoint is attacked in two different shapes
and one limit only stops one of them:

  * `LoginIPThrottle` caps attempts from a single address. It stops someone
    working through a password list against one account, or through an email
    list from one machine.

  * `LoginEmailThrottle` caps attempts against a single account, whatever
    address they come from. Without it, a botnet with a thousand addresses
    gets a thousand times the budget against one manager's account, and the
    per-IP limit never fires.

Both are needed. Either alone leaves the other attack untouched.
"""

from rest_framework.throttling import SimpleRateThrottle


class LoginIPThrottle(SimpleRateThrottle):
    scope = "login_ip"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class LoginEmailThrottle(SimpleRateThrottle):
    """Keyed on the email being attempted, not on the caller.

    The address is lowercased so that MANAGER@... and manager@... share one
    budget -- the accounts are the same account (the model's uniqueness is on
    Lower(email)), so their rate limits have to be the same limit too.
    """

    scope = "login_email"

    def get_cache_key(self, request, view):
        email = request.data.get("email") if hasattr(request, "data") else None
        if not isinstance(email, str) or not email.strip():
            # Nothing to key on. Returning None skips this throttle rather
            # than lumping every malformed request under one shared bucket,
            # which would let junk requests exhaust a real user's budget.
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": email.strip().lower(),
        }
