"""Item list filtering. Everything here resolves to SQL (goal 6)."""

from apps.stock.models import Location

# An allow-list, not a passthrough. Handing user input straight to order_by
# lets anyone sort by any field or traverse a relation -- an information
# disclosure surface, and a 500 the first time someone sends nonsense.
SORTS = {
    "name": "name",
    "-name": "-name",
    "sku": "sku",
    "-sku": "-sku",
    "on_hand": "on_hand",
    "-on_hand": "-on_hand",
    "reorder_level": "reorder_level",
    "-reorder_level": "-reorder_level",
}
DEFAULT_SORT = "name"


def _as_int(value):
    """Query params arrive as strings from a URL anyone can edit. Passing one
    straight into a pk lookup raises ValueError out of the field coercion,
    which surfaces as a 500 -- so coerce here and let the caller decide what a
    junk value means."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def apply_filters(queryset, params):
    """Order matters: with_on_hand() must run before at_or_below_reorder(),
    which references the annotation it adds."""
    location = None
    location_id = params.get("location")
    if location_id:
        pk = _as_int(location_id)
        location = Location.objects.filter(pk=pk).first() if pk is not None else None
        if location:
            # Restrict to items with activity at this location. Combined with
            # with_on_hand(location) below, each row then shows that shelf's
            # quantity rather than the global total.
            queryset = queryset.filter(ledger_entries__location=location).distinct()
        else:
            # An unknown id returns nothing rather than falling through to an
            # unfiltered list. Silently ignoring the filter would show global
            # quantities labelled as one location's -- the exact kind of quiet
            # wrongness this system exists to prevent. Returning early is safe:
            # with no rows there is nothing left to annotate or sort.
            return queryset.none()

    queryset = queryset.search(params.get("q", "").strip())

    category = params.get("category")
    if category:
        category_pk = _as_int(category)
        if category_pk is None:
            # Same reasoning as an unknown location: a filter that cannot be
            # honoured must not quietly become no filter at all.
            return queryset.none()
        queryset = queryset.filter(category_id=category_pk)

    archived = params.get("archived")
    if archived == "1":
        queryset = queryset.filter(is_archived=True)
    elif archived == "all":
        pass
    else:
        # Archived items drop out of day-to-day lists by default (goal 2).
        # They keep their history; they just stop cluttering the working view.
        queryset = queryset.filter(is_archived=False)

    queryset = queryset.with_on_hand(location=location)

    if params.get("below_reorder") == "1":
        queryset = queryset.at_or_below_reorder()

    sort = SORTS.get(params.get("sort", ""), DEFAULT_SORT)
    # The id tiebreaker is not decoration: without it two items with the same
    # name have no guaranteed order, and page 2 can repeat a row from page 1.
    return queryset.order_by(sort, "id")
