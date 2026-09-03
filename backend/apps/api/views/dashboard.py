"""The dashboard (goal 8).

One request rather than six. The tiles are read together and each aggregate is
cheap, so splitting them would cost six round trips on a cold Render instance
to save nothing.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.serializers import MovementSerializer
from apps.stock.services import dashboard_service as ds


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    return Response(
        {
            **ds.headline_numbers(),
            "total_on_hand": ds.total_on_hand(),
            "by_category": ds.on_hand_by_category(),
            "by_location": ds.on_hand_by_location(),
            "weekly": ds.movement_volume_by_week(),
            "recent": MovementSerializer(ds.recent_movements(), many=True).data,
        }
    )
