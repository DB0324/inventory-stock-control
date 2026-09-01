from rest_framework import serializers

from apps.stock.models import Location


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