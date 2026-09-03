from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.api.serializers import LoginSerializer, MeSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    """Hands the client a CSRF token before it posts anything.

    The token is returned in the *body*, not only as a cookie, and that is
    the load-bearing part in production. The SPA is served from a different
    domain than this API, so document.cookie on the frontend origin cannot
    see a cookie set for the API's domain -- the browser sends it, but
    JavaScript there cannot read it. Reading the cookie works only in
    development, where both sides are localhost.

    Returning it in the body is safe. A CSRF token is not a credential: it
    proves the request came from a page that could read this response, which
    is exactly what we want to establish. The session cookie stays HttpOnly
    and is never exposed here.
    """
    return Response({"csrftoken": get_token(request)})


@api_view(["POST"])
@permission_classes([AllowAny])
def login_view(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    user = authenticate(
        request,
        username=serializer.validated_data["email"].lower(),
        password=serializer.validated_data["password"],
    )
    if user is None:
        # One message for both wrong-email and wrong-password. Distinguishing
        # them tells an attacker which addresses are registered.
        return Response(
            {"detail": "Incorrect email or password."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    login(request, user)
    return Response(MeSerializer(user).data)


@api_view(["POST"])
def logout_view(request):
    logout(request)
    return Response({"detail": "ok"})


@api_view(["GET"])
def me(request):
    return Response(MeSerializer(request.user).data)