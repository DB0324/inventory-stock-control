from rest_framework import viewsets

from apps.api.serializers import LocationSerializer
from apps.api.views.catalog import ManagerWritesMixin
from apps.stock.models import Location


class LocationViewSet(ManagerWritesMixin, viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer