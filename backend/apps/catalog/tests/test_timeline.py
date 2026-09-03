"""Tests U-43 to U-50: the timeline.

Goal 9 says nothing here can be edited or deleted, including by managers, so
the mutation tests hit the database directly rather than going through the
model.
"""

import pytest
from django.db import DatabaseError, connection

from apps.catalog.models import ItemTimelineEvent
from apps.catalog.services import timeline_service as ts


def test_created_event(manager, item):
    ts.record_created(item=item, actor=manager)
    event = item.timeline.get()
    assert event.event_type == "CREATED"
    assert event.actor == manager


def test_rename_records_old_and_new(manager, item):
    """U-44. The old value must be captured before the save -- reading the
    instance afterwards gives the new value twice."""
    before = ts.snapshot(item)
    item.name = "Hex bolt M10"
    item.save()
    ts.record_changes(item=item, actor=manager, before=before)

    event = item.timeline.get()
    assert event.field_name == "name"
    assert event.old_value == "Hex bolt M8"
    assert event.new_value == "Hex bolt M10"


def test_two_fields_produce_two_events(manager, item):
    before = ts.snapshot(item)
    item.name = "Renamed"
    item.reorder_level = 99
    item.save()
    ts.record_changes(item=item, actor=manager, before=before)

    fields = {e.field_name for e in item.timeline.all()}
    assert fields == {"name", "reorder_level"}


def test_no_change_produces_no_event(manager, item):
    before = ts.snapshot(item)
    item.save()
    ts.record_changes(item=item, actor=manager, before=before)
    assert item.timeline.count() == 0


def test_note_joins_the_same_timeline(manager, item):
    ts.record_created(item=item, actor=manager)
    ts.record_note(item=item, actor=manager, body="Damaged box on arrival")
    types = {e.event_type for e in item.timeline.all()}
    assert types == {"CREATED", "NOTE"}


def test_empty_note_rejected(manager, item):
    with pytest.raises(ValueError):
        ts.record_note(item=item, actor=manager, body="   ")


def test_category_rename_does_not_rewrite_history(manager, item, category):
    """U-48. old_value is text, not a foreign key, so renaming the category
    later must not change what this entry says."""
    before = ts.snapshot(item)
    item.name = "Renamed"
    item.save()
    ts.record_changes(item=item, actor=manager, before=before)

    category.name = "Hardware"
    category.save()

    assert item.timeline.get().old_value == "Hex bolt M8"


def test_timeline_update_blocked_by_trigger(manager, item):
    ts.record_created(item=item, actor=manager)
    event = item.timeline.get()
    with pytest.raises(DatabaseError):
        ItemTimelineEvent.objects.filter(pk=event.pk).update(note_body="tampered")


def test_timeline_delete_blocked_by_trigger(manager, item):
    ts.record_created(item=item, actor=manager)
    event = item.timeline.get()
    with pytest.raises(DatabaseError), connection.cursor() as cur:
        cur.execute(
            "DELETE FROM catalog_item_timeline_event WHERE id = %s", [event.pk]
        )