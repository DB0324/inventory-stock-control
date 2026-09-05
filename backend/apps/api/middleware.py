"""Response headers the whole API needs.

Two things, both about the same underlying fact: every /api/ response is
specific to the signed-in user, and nothing in the chain between here and the
browser should be allowed to forget that.
"""


class ApiCacheControlMiddleware:
    """`Cache-Control: no-store` on every API response.

    Without it a response carrying one user's stock positions can be held in
    the browser's disk cache and in any shared proxy along the way. Two
    concrete consequences:

      * Sign out, press Back, and the previous user's data renders from cache.
        The session is gone, but the page was never re-requested.
      * A shared cache that keys only on the URL can serve one user's
        /api/items/ to the next user, since the URL is identical and only the
        cookie differs.

    `no-store` is the strong form -- do not write this to disk at all -- rather
    than `no-cache`, which permits storing it and only requires revalidation.
    For data that should not survive a sign-out, not storing it is the point.

    This is deliberately blanket rather than per-view. Cache headers are the
    kind of thing that is correct on the endpoint someone remembered and
    missing on the one added later, and the endpoint they forget is the one
    that leaks. The client already caches in memory through TanStack Query,
    which is scoped to the tab and cleared on logout, so nothing here costs a
    round trip that was actually being saved.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/api/"):
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response["Pragma"] = "no-cache"
            # Vary on Cookie so that any cache which ignores the above at
            # least keys on the session rather than on the URL alone.
            existing = response.get("Vary", "")
            if "cookie" not in existing.lower():
                response["Vary"] = f"{existing}, Cookie".strip(", ")
        return response
