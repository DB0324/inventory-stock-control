"""Maps service-layer exceptions to HTTP.

The interesting one is InsufficientStock -> 409. It is not a validation error:
the request was well-formed, and the identical request could succeed a minute
later once stock arrives. 400 would tell the client to fix its input, which
is wrong advice.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_handler

from apps.stock.services.exceptions import (
    EditConflict, InsufficientStock, ItemArchived, LocationNotAssigned,
)


def handler(exc, context):
    if isinstance(exc, InsufficientStock):
        return Response({"detail": str(exc), "code": "insufficient_stock"},
                        status=status.HTTP_409_CONFLICT)

    if isinstance(exc, EditConflict):
        return Response({"detail": str(exc), "code": "edit_conflict"},
                        status=status.HTTP_409_CONFLICT)

    if isinstance(exc, LocationNotAssigned):
        return Response({"detail": str(exc), "code": "location_not_assigned"},
                        status=status.HTTP_403_FORBIDDEN)

    if isinstance(exc, ItemArchived):
        return Response({"detail": str(exc), "code": "item_archived"},
                        status=status.HTTP_409_CONFLICT)

    if isinstance(exc, ValueError) and not isinstance(exc, KeyError):
        return Response({"detail": str(exc), "code": "invalid"},
                        status=status.HTTP_400_BAD_REQUEST)

    return drf_handler(exc, context)