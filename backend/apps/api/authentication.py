from rest_framework.authentication import SessionAuthentication


class CsrfSessionAuthentication(SessionAuthentication):
    """SessionAuthentication, but producing 401 rather than 403 for anonymous
    requests. CSRF enforcement is unchanged -- the parent still runs it."""

    def authenticate_header(self, request):
        return "Session"