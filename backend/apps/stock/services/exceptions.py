class StockError(Exception):
    """Base for anything the stock service refuses to do."""


class InsufficientStock(StockError):
    """A movement would drive a location's balance negative.

    Distinct from a validation error: the request was well-formed, and the
    same request could succeed later. Maps to HTTP 409, not 400.
    """


class ItemArchived(StockError):
    """Archived items keep their history but reject new movements."""


class LocationNotAssigned(StockError):
    """Staff may only record movements where they are assigned. Maps to 403."""


class EditConflict(Exception):
    """Someone else changed the record between it being read and saved.

    Deliberately not a StockError: nothing about the ledger is involved. Like
    InsufficientStock it maps to 409 rather than 400, for the same reason --
    the request was well-formed, and retrying it against the current version
    would succeed.
    """
