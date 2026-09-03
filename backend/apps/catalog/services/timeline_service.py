"""Writes to the item timeline. Nothing else may."""

from apps.catalog.models import Item, ItemTimelineEvent

# Only these are audited. created_at and updated_at are noise, and sku is
# immutable in practice -- changing it would break every label already printed.
TRACKED_FIELDS = ["name", "description", "unit_of_measure", "reorder_level", "category"]


def record_created(*, item, actor):
    ItemTimelineEvent.objects.create(
        item=item, event_type=ItemTimelineEvent.EventType.CREATED, actor=actor,
    )


def record_changes(*, item, actor, before: dict):
    """One event per changed field, with the value as it was.

    `before` must be captured BEFORE the save. Reading the instance afterwards
    gives you the new values twice, and you silently write events saying
    name: "Widget" -> "Widget".
    """
    events = []
    for field in TRACKED_FIELDS:
        old = before.get(field)
        new = _display(getattr(item, field))
        if old == new:
            continue
        events.append(ItemTimelineEvent(
            item=item,
            event_type=ItemTimelineEvent.EventType.FIELD_CHANGE,
            field_name=field, old_value=old, new_value=new, actor=actor,
        ))
    ItemTimelineEvent.objects.bulk_create(events)
    return events


def snapshot(item: Item) -> dict:
    """Values as text, taken before a save."""
    return {f: _display(getattr(item, f)) for f in TRACKED_FIELDS}


def record_note(*, item, actor, body):
    if not body or not body.strip():
        raise ValueError("A note cannot be empty.")
    return ItemTimelineEvent.objects.create(
        item=item, event_type=ItemTimelineEvent.EventType.NOTE,
        note_body=body.strip(), actor=actor,
    )


def record_archived(*, item, actor, restored=False):
    ItemTimelineEvent.objects.create(
        item=item,
        event_type=(ItemTimelineEvent.EventType.RESTORED if restored
                    else ItemTimelineEvent.EventType.ARCHIVED),
        actor=actor,
    )


def _display(value):
    return None if value is None else str(value)