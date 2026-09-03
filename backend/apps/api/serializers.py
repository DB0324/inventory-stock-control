from django.contrib.auth import get_user_model
from rest_framework import serializers
from apps.catalog.models import Category, Item, ItemTimelineEvent
from apps.stock.models import Location, LocationAssignment, StockMovement


class LocationBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "code", "name"]


class MeSerializer(serializers.Serializer):
    """Everything the client needs to render the right UI for this user.

    Assigned locations are included so the movement forms can scope their
    dropdowns without a second request. Managers get every active location,
    because they hold no assignment rows at all -- their access is universal
    by role, so it cannot be revoked by deleting one.
    """

    id = serializers.IntegerField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    role = serializers.CharField()
    is_manager = serializers.BooleanField()
    locations = serializers.SerializerMethodField()

    def get_locations(self, user):
        if user.is_manager:
            qs = Location.objects.filter(is_active=True)
        else:
            qs = Location.objects.filter(
                assignments__user=user, is_active=True,
            ).distinct()
        return LocationBriefSerializer(qs, many=True).data


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(style={"input_type": "password"})


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "is_active"]

    def validate_name(self, value):
        """The model's uniqueness is a functional index on Lower(name), and
        DRF cannot infer a validator from one -- it only reads unique=True on
        the field. Without this the database raises IntegrityError and the
        manager gets a 500 for the most ordinary mistake there is: adding a
        category that already exists in different capitalisation.
        """
        name = value.strip()
        if not name:
            raise serializers.ValidationError("A category needs a name.")

        clash = Category.objects.filter(name__iexact=name)
        if self.instance:
            # A rename that only changes capitalisation must still be allowed,
            # so the row being edited cannot clash with itself.
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(
                f"A category called {clash.first().name!r} already exists."
            )
        return name


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "code", "name", "is_active"]


class ItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    on_hand = serializers.IntegerField(read_only=True)

    class Meta:
        model = Item
        fields = [
            "id", "sku", "name", "description", "unit_of_measure",
            "reorder_level", "category", "category_name", "is_archived",
            "on_hand", "created_at", "updated_at",
        ]
        read_only_fields = ["is_archived", "created_at", "updated_at"]


class TimelineEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True)

    class Meta:
        model = ItemTimelineEvent
        fields = [
            "id", "event_type", "field_name", "old_value", "new_value",
            "note_body", "actor_name", "created_at",
        ]


class MovementSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.CharField(
        source="recorded_by.full_name", read_only=True)
    location_code = serializers.CharField(
        source="location.code", read_only=True, default=None)
    source_code = serializers.CharField(
        source="source_location.code", read_only=True, default=None)
    destination_code = serializers.CharField(
        source="destination_location.code", read_only=True, default=None)

    class Meta:
        model = StockMovement
        fields = [
            "id", "kind", "quantity", "location_code", "source_code",
            "destination_code", "reason", "note", "recorded_by_name",
            "recorded_at",
        ]


class NoteSerializer(serializers.Serializer):
    body = serializers.CharField()


# --- Movement input: four flat serializers, not one with conditionals ------
# ADR-010. Each kind has different required fields, and a single serializer
# with branching validation is where required-field bugs hide.

class ReceiptInputSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    location = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class IssueInputSerializer(ReceiptInputSerializer):
    pass


class AdjustmentInputSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    location = serializers.IntegerField()
    quantity = serializers.IntegerField()   # signed
    reason = serializers.CharField()        # goal 4: mandatory
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_quantity(self, value):
        if value == 0:
            raise serializers.ValidationError("Adjustment cannot be zero.")
        return value


class TransferInputSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    source = serializers.IntegerField()
    destination = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["source"] == attrs["destination"]:
            raise serializers.ValidationError(
                {"destination": "Source and destination must differ."})
        return attrs

class AssignmentSerializer(serializers.ModelSerializer):
    """One staff-to-location grant.

    assigned_by is read-only and taken from the request. Letting a client name
    the grantor would make the audit trail forgeable, which is the one thing
    this table exists to prevent.
    """

    location_code = serializers.CharField(source="location.code", read_only=True)
    assigned_by_name = serializers.CharField(
        source="assigned_by.full_name", read_only=True
    )

    class Meta:
        model = LocationAssignment
        fields = [
            "id", "user", "location", "location_code",
            "assigned_by_name", "assigned_at",
        ]
        read_only_fields = ["assigned_at"]


class StaffSerializer(serializers.ModelSerializer):
    """A staff member and the locations they may record movements at.

    Managers are excluded from the list this feeds. They hold no assignment
    rows at all -- their reach is universal by role, so showing checkboxes for
    them would imply an access model that does not exist.
    """

    assignments = AssignmentSerializer(source="location_assignments", many=True,
                                       read_only=True)

    class Meta:
        model = get_user_model()
        fields = ["id", "email", "full_name", "role", "is_active", "assignments"]
