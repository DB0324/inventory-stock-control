"""Four endpoints, one per movement kind (ADR-010).

Each maps to one service function. The service owns the transaction, the
advisory lock, the negative-stock check and the location check -- so the CSV
importer and the seed command enforce identical rules without duplicating
any of them here.
"""

from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.api.permissions import CanRecordMovement, IsManager
from apps.api.serializers import (
    AdjustmentInputSerializer, IssueInputSerializer, MovementSerializer,
    ReceiptInputSerializer, TransferInputSerializer,
)
from apps.catalog.models import Item
from apps.stock.models import Location
from apps.stock.services import stock_service as ss


def _validated(serializer_class, request):
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _response(movement, item, locations):
    """Return the movement plus the balances it changed.

    Saves the client a refetch, and guarantees the number it displays came out
    of a SQL aggregate rather than client-side arithmetic.
    """
    return Response(
        {
            "movement": MovementSerializer(movement).data,
            "on_hand": {loc.code: ss.on_hand(item, loc) for loc in locations},
            "on_hand_total": ss.on_hand(item),
        },
        status=201,
    )


@api_view(["POST"])
@permission_classes([CanRecordMovement])
def receipt(request):
    data = _validated(ReceiptInputSerializer, request)
    item = get_object_or_404(Item, pk=data["item"])
    location = get_object_or_404(Location, pk=data["location"])
    movement = ss.record_receipt(
        actor=request.user, item=item, location=location,
        quantity=data["quantity"], note=data["note"],
    )
    return _response(movement, item, [location])


@api_view(["POST"])
@permission_classes([CanRecordMovement])
def issue(request):
    data = _validated(IssueInputSerializer, request)
    item = get_object_or_404(Item, pk=data["item"])
    location = get_object_or_404(Location, pk=data["location"])
    movement = ss.record_issue(
        actor=request.user, item=item, location=location,
        quantity=data["quantity"], note=data["note"],
    )
    return _response(movement, item, [location])


@api_view(["POST"])
@permission_classes([IsManager])
def adjustment(request):
    """Manager-only. Goal 1 says staff cannot create adjustments -- an
    adjustment is the one movement that admits the records were wrong."""
    data = _validated(AdjustmentInputSerializer, request)
    item = get_object_or_404(Item, pk=data["item"])
    location = get_object_or_404(Location, pk=data["location"])
    movement = ss.record_adjustment(
        actor=request.user, item=item, location=location,
        quantity=data["quantity"], reason=data["reason"], note=data["note"],
    )
    return _response(movement, item, [location])


@api_view(["POST"])
@permission_classes([CanRecordMovement])
def transfer(request):
    data = _validated(TransferInputSerializer, request)
    item = get_object_or_404(Item, pk=data["item"])
    source = get_object_or_404(Location, pk=data["source"])
    destination = get_object_or_404(Location, pk=data["destination"])
    movement = ss.record_transfer(
        actor=request.user, item=item, source=source,
        destination=destination, quantity=data["quantity"], note=data["note"],
    )
    return _response(movement, item, [source, destination])