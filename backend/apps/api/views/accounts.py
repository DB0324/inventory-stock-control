"""Account administration.

There is no sign-up page, and that is a decision rather than an omission.

In an inventory system the user list *is* the permissions list. Self-service
registration would mean anyone who finds the URL becomes an authenticated
principal, and even a brand-new STAFF account with no location assignments can
read the whole catalogue, every stock position and every movement. Read access
to that is exactly the commercial information the system holds. So accounts are
created by a manager, the same person who already decides who may act where
(goal 5) -- it is the same decision, made in the same place.

Kept apart from StaffViewSet on purpose. That endpoint feeds the assignment
grid and deliberately excludes managers, because managers hold no assignment
rows; this one has to show every account, including the managers, or you could
not tell who has manager access. Two questions, two endpoints.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.api.permissions import IsManager


class AccountSerializer(serializers.ModelSerializer):
    """Read shape. No password field of any kind -- not even write_only, so
    that this serializer can never be the thing that changes one by accident.
    Creation uses its own serializer below."""

    class Meta:
        model = get_user_model()
        fields = ["id", "email", "full_name", "role", "is_active", "date_joined"]
        read_only_fields = fields


class AccountCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = get_user_model()
        fields = ["id", "email", "full_name", "role", "password"]

    def validate_email(self, value):
        """The model enforces this with a functional index on Lower(email),
        which DRF cannot see -- it only infers a uniqueness validator from
        unique=True on the field. Without this check the database raises
        IntegrityError and a manager gets a 500 for a typo."""
        email = value.strip().lower()
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                "An account with that email address already exists."
            )
        return email

    def validate_password(self, value):
        """Django's configured validators, not a length check invented here.
        Running them at the boundary means the message names the actual
        problem -- too short, too common, too similar to the email.
        """
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def create(self, validated_data):
        # create_user, not objects.create: the plain create() would store the
        # password as clear text in the hash column, and the account would
        # then be unable to log in with it either.
        return get_user_model().objects.create_user(**validated_data)


class AccountViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """List, create, deactivate, reactivate. Deliberately no destroy.

    Movements point at their recorder with PROTECT, so deleting an account
    that has ever recorded anything is refused by the database -- correctly,
    because the alternative is a ledger whose entries have no author. What a
    departing employee actually needs is their access revoked, which is what
    deactivate does, and their history stays intact and attributed.
    """

    permission_classes = [IsManager]

    def get_queryset(self):
        return get_user_model().objects.order_by("full_name", "id")

    def get_serializer_class(self):
        if self.action == "create":
            return AccountCreateSerializer
        return AccountSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # Answer with the read shape. The create serializer's fields are the
        # input contract and include a password key; echoing that shape back
        # invites a client to hold onto it.
        return Response(
            AccountSerializer(user).data, status=status.HTTP_201_CREATED
        )

    def _set_active(self, request, pk, active):
        user = self.get_object()
        # A manager who deactivates their own account is locked out with no
        # way back in short of a shell on the server. The guard is here rather
        # than in the UI because hiding the button is not enforcement.
        if user == request.user:
            return Response(
                {"detail": "You cannot change your own account's access."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if user.is_active != active:
            user.is_active = active
            user.save(update_fields=["is_active"])
        return Response(AccountSerializer(user).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        return self._set_active(request, pk, active=False)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        return self._set_active(request, pk, active=True)
