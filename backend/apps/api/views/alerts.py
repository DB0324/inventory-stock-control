"""Low-stock alerts (goal 10).

Reads are open to any authenticated user -- staff need to know what is running
out in order to do anything about it. Dismissing is manager-only, because the
brief says so and because a dismissal hides information from everyone else.
"""

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.permissions import IsManager
from apps.api.serializers import ItemSerializer
from apps.catalog.models import Item
from apps.stock.services import alert_service


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def list_alerts(request):
    """Paginated, because a neglected catalogue can have a lot of these."""
    queryset = alert_service.active_alerts()
    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(queryset, request)
    return paginator.get_paginated_response(
        ItemSerializer(page, many=True).data
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def alert_count(request):
    """Just the number, for the navigation badge.

    A separate endpoint rather than reading `count` off the list, so the badge
    does not pay for a page of serialized items on every screen that shows it.
    """
    return Response({"count": alert_service.alert_count()})


@api_view(["POST"])
@permission_classes([IsManager])
def dismiss_alert(request, item_id):
    """Acknowledge one item's alert.

    Returns the item, so the client can drop it from the list without a
    refetch. Dismissing an item that is not currently alerting is allowed and
    harmless -- the dismissal simply has nothing to suppress, and will lapse
    the moment stock recovers like any other.
    """
    item = get_object_or_404(Item, pk=item_id)
    alert_service.dismiss(item=item, actor=request.user)

    # Re-read through the annotated queryset so the response carries on_hand,
    # which ItemSerializer expects and a plain instance would not have.
    refreshed = Item.objects.with_on_hand().get(pk=item.pk)
    return Response(ItemSerializer(refreshed).data)
