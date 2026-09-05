# Schema

Nine application tables, plus Django's own (`django_session`, `django_migrations`,
the admin log and permission tables) and one cache table. PostgreSQL 17.

## Tables

### `accounts_user`
| Column | Type | Notes |
|---|---|---|
| id | bigint | PK |
| email | varchar(254) | unique on `Lower(email)` |
| full_name | varchar(150) | |
| role | varchar(16) | `MANAGER` or `STAFF` |
| password | varchar(128) | Django hash |
| is_active | boolean | deactivating revokes sign-in |
| is_staff | boolean | Django admin only, unrelated to the STAFF role |
| date_joined | timestamptz | |

### `catalog_category`
| Column | Type | Notes |
|---|---|---|
| id | bigint | PK |
| name | varchar(80) | unique on `Lower(name)` |
| is_active | boolean | |
| created_at | timestamptz | |

### `catalog_item`
| Column | Type | Notes |
|---|---|---|
| id | bigint | PK |
| sku | varchar(64) | unique on `Upper(sku)` |
| name | varchar(200) | |
| description | text | |
| unit_of_measure | varchar(16) | |
| reorder_level | integer | `>= 0` |
| category_id | bigint | FK → category, PROTECT |
| version | integer | optimistic-lock token |
| is_archived | boolean | |
| created_at, updated_at | timestamptz | |

**No quantity column.** On-hand is always derived.

### `catalog_item_timeline_event`
| Column | Type | Notes |
|---|---|---|
| id | bigint | PK |
| item_id | bigint | FK → item, PROTECT |
| event_type | varchar(16) | CREATED / FIELD_CHANGE / NOTE / ARCHIVED / RESTORED |
| field_name, old_value, new_value | text | field changes only |
| note_body | text | notes only |
| actor_id | bigint | FK → user, PROTECT |
| created_at | timestamptz | |

### `stock_location`
| Column | Type | Notes |
|---|---|---|
| id | bigint | PK |
| code | varchar(20) | unique |
| name | varchar(120) | |
| is_active | boolean | |
| created_at | timestamptz | |

### `stock_location_assignment`
| Column | Type | Notes |
|---|---|---|
| id | bigint | PK |
| user_id | bigint | FK → user, CASCADE |
| location_id | bigint | FK → location, CASCADE |
| assigned_by_id | bigint | FK → user, PROTECT |
| assigned_at | timestamptz | |

### `stock_movement` — the event
| Column | Type | Notes |
|---|---|---|
| id | bigint | PK |
| item_id | bigint | FK → item, PROTECT |
| kind | varchar(16) | RECEIPT / ISSUE / TRANSFER / ADJUSTMENT |
| quantity | integer | non-zero |
| location_id | bigint null | set for all kinds except transfer |
| source_location_id | bigint null | transfers only |
| destination_location_id | bigint null | transfers only |
| reason | text null | mandatory for adjustments |
| note | text | |
| recorded_by_id | bigint | FK → user, PROTECT |
| recorded_at | timestamptz | |

### `stock_ledger_entry` — the effect
| Column | Type | Notes |
|---|---|---|
| id | bigint | PK |
| movement_id | bigint | FK → movement, PROTECT |
| item_id | bigint | FK → item, PROTECT |
| location_id | bigint | FK → location, PROTECT |
| delta | integer | non-zero, signed |
| occurred_at | timestamptz | |

One movement writes one entry, except a transfer, which writes two summing
to zero.

### `stock_low_stock_dismissal`
| Column | Type | Notes |
|---|---|---|
| id | bigint | PK |
| item_id | bigint | FK → item, PROTECT |
| dismissed_by_id | bigint | FK → user, PROTECT |
| dismissed_at | timestamptz | |
| reorder_level | integer | the level at the time of dismissal |
| cleared_at | timestamptz null | set when stock recovers |

### `cache_table`

Not a model. Created by `manage.py createcachetable`, which `build.sh` runs on
every deploy, and used only by the login rate limiter. It is in the database
rather than in process memory because a per-process cache means each gunicorn
worker keeps its own attempt counter, and "five attempts a minute" quietly
becomes five per worker.

## Relationships

**One-to-many:** category → items; item → movements; item → timeline events;
item → dismissals; movement → ledger entries; location → ledger entries;
user → movements recorded.

**Many-to-many:** users ↔ locations, through `stock_location_assignment`. It is
an explicit table rather than a Django `ManyToManyField` because the grant
carries data of its own — who granted it and when — and that audit trail is
the point of the table.

## Database vs application

**In the database:**
- Case-insensitive uniqueness on email, SKU and category name (functional
  unique indexes on `Lower`/`Upper`).
- `reorder_level >= 0`, `quantity <> 0`, `delta <> 0`.
- Movement shape: a transfer has source and destination and no location; every
  other kind has a location and neither of the other two.
- Adjustments must carry a reason.
- One active dismissal per item (partial unique index on `cleared_at IS NULL`).
- **Immutability:** `BEFORE UPDATE OR DELETE` triggers on `stock_movement`,
  `stock_ledger_entry` and `catalog_item_timeline_event` raise an exception.

**In application code:**
- Sufficient stock at a location.
- Role permissions and location assignment.
- Archived items reject new movements.
- Login rate limits, and the CSV export's formula-prefix guard.

The line is: **anything whose violation would corrupt history goes in the
database.** Those rules must hold against a psql session, a future script, or a
bug in my own code — enforcement that a `WHERE` clause can bypass is not
enforcement. Rules that need to read a computed balance, or produce a helpful
message, live in the service layer, with a database constraint underneath
wherever one is possible.

## Deliberate denormalisation

Almost none, with two exceptions:

- `stock_ledger_entry.item_id` duplicates what could be reached through
  `movement_id`. It is there so the on-hand aggregate never joins to
  `stock_movement` — the hot query stays on one table and one index.
- `stock_low_stock_dismissal.reorder_level` copies the item's level at the
  moment of dismissal. That copy is what lets a raised reorder level re-arm a
  dismissed alert.

## What breaks first at 100× the data

`SUM(delta)` per item. It is indexed on `(item_id, location_id)` and fine into
the millions of rows, but it grows forever, and the item list computes it for
every row on the page.

The fix, when it is needed, is periodic checkpoint rows so the sum only covers
entries after the checkpoint — still derived, still rebuildable from the ledger,
never authoritative. Not built: the trigger to build it is item-list p95 over
300 ms, or any single item passing ~100k ledger entries. `test_query_counts.py`
pins the query *shape* meanwhile, so a page cannot silently become an N+1.

Second in line is the `pg_trgm` GIN index for substring search, which is large
and write-amplifying. At that scale full-text search or a search service would
replace it.
