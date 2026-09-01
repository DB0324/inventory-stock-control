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
    """Hands the client a CSRF cookie before it posts anything.

    The client cannot read an HttpOnly cookie, so CSRF_COOKIE_HTTPONLY is
    False -- it has to read the token and echo it in a header. That is safe:
    the token is not a credential, and the session cookie stays HttpOnly.
    """
    get_token(request)
    return Response({"detail": "ok"})


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