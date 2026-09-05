"""Categories and items.

Writes are manager-only (goal 1). Reads are open to any authenticated user,
because staff need the item list to record movements against.
"""

from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.api.filters import apply_filters
from apps.api.permissions import IsManager
from apps.api.serializers import (
    CategorySerializer, ItemSerializer, MovementSerializer,
    NoteSerializer, TimelineEventSerializer,
)
from apps.catalog.models import Category, Item
from apps.catalog.services import timeline_service as ts
from apps.stock.services.exceptions import EditConflict


class ManagerWritesMixin:
    """Anyone signed in may read. Only managers may write.
    Actions that declare their own permission_classes keep them -- notes are
    a POST but staff may leave them (goal 9 puts notes in the timeline and
    does not restrict them to managers).
    """

    def get_permissions(self):
        # self.action is None when the method doesn't match a route -- a PUT
        # to a GET-only action, for instance. DRF will return 405 shortly;
        # we just need to not crash before it gets there.
        handler = getattr(self, self.action, None) if self.action else None
        declared = getattr(handler, "kwargs", {}).get("permission_classes")
        if declared:
            return [p() for p in declared]
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return [IsManager()]


class CategoryViewSet(ManagerWritesMixin, viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ItemViewSet(ManagerWritesMixin, viewsets.ModelViewSet):
    serializer_class = ItemSerializer

    def get_queryset(self):
        # on_hand is annotated in SQL, never summed in Python -- the moment
        # one screen adds up a movement list, two screens disagree.
        base = Item.objects.select_related("category")
        if self.action == "list":
            return apply_filters(base, self.request.query_params)
        # Detail routes still need on_hand, but none of the filtering: a
        # search term must not be able to make a valid item 404.
        return base.with_on_hand().order_by("name", "id")

    def perform_create(self, serializer):
        # A brand new item has nothing to conflict with, so the field is
        # meaningless here -- but it has to be discarded rather than ignored,
        # or it reaches Item(**validated_data) as an unknown keyword.
        serializer.validated_data.pop("expected_version", None)
        item = serializer.save()
        ts.record_created(item=item, actor=self.request.user)

    @transaction.atomic
    def perform_update(self, serializer):
        expected = serializer.validated_data.pop("expected_version", None)

        # Re-read under a row lock. Without the lock this is a check-then-act:
        # two requests could both read version 3, both find it matches, and
        # both write version 4 -- which is the race the version field exists
        # to close. The lock is held for the length of this method, not for
        # the length of a human editing a form.
        current = Item.objects.select_for_update().get(pk=serializer.instance.pk)

        if expected is not None and expected != current.version:
            raise EditConflict(
                "Someone else changed this item while you were editing it. "
                "Reload to see their changes, then apply yours."
            )

        # Snapshot BEFORE the save, and from the locked row rather than the
        # serializer's copy. Reading the instance afterwards gives the new
        # values twice, and you write events saying name: "X" -> "X".
        before = ts.snapshot(current)
        item = serializer.save(version=current.version + 1)
        ts.record_changes(item=item, actor=self.request.user, before=before)

    @action(detail=True, methods=["post"], permission_classes=[IsManager])
    def archive(self, request, pk=None):
        item = self.get_object()
        if not item.is_archived:
            item.is_archived = True
            item.save(update_fields=["is_archived", "updated_at"])
            ts.record_archived(item=item, actor=request.user)
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"], permission_classes=[IsManager])
    def restore(self, request, pk=None):
        item = self.get_object()
        if item.is_archived:
            item.is_archived = False
            item.save(update_fields=["is_archived", "updated_at"])
            ts.record_archived(item=item, actor=request.user, restored=True)
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["get"])
    def movements(self, request, pk=None):
        qs = (
            self.get_object().movements
            .select_related("recorded_by", "location",
                            "source_location", "destination_location")
        )
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(
            MovementSerializer(page, many=True).data)

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        """Read-only. There is no write route here and there never will be --
        goal 9 says nothing in it can be edited or deleted."""
        qs = self.get_object().timeline.select_related("actor")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(
            TimelineEventSerializer(page, many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated])
    def notes(self, request, pk=None):
        """Staff may leave notes -- goal 9 says notes are part of the timeline,
        and it does not restrict them to managers."""
        serializer = NoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = ts.record_note(
            item=self.get_object(), actor=request.user,
            body=serializer.validated_data["body"],
        )
        return Response(TimelineEventSerializer(event).data, status=201)