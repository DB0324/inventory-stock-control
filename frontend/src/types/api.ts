export type Role = "MANAGER" | "STAFF";

export interface LocationBrief {
  id: number;
  code: string;
  name: string;
}

/** The full row from /api/locations/. LocationBrief is the trimmed version
 *  embedded in /me/, which deliberately omits is_active -- a user is only
 *  ever given active locations. */
export interface Location extends LocationBrief {
  is_active: boolean;
}

export interface Me {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_manager: boolean;
  /** Every active location for managers; assigned ones only for staff.
   *  Movement form dropdowns read from this, which is why the server sends
   *  it with /me/ rather than making the client ask a second time. */
  locations: LocationBrief[];
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Category {
  id: number;
  name: string;
  is_active: boolean;
}

export interface Item {
  id: number;
  sku: string;
  name: string;
  description: string;
  unit_of_measure: string;
  reorder_level: number;
  category: number;
  category_name: string;
  is_archived: boolean;
  /** Always from a SQL aggregate. Never computed in the client -- the moment
   *  one screen sums a movement list, two screens disagree. */
  on_hand: number;
  created_at: string;
  updated_at: string;
}

export type MovementKind = "RECEIPT" | "ISSUE" | "TRANSFER" | "ADJUSTMENT";

export interface Movement {
  id: number;
  kind: MovementKind;
  quantity: number;
  location_code: string | null;
  source_code: string | null;
  destination_code: string | null;
  reason: string | null;
  note: string;
  recorded_by_name: string;
  recorded_at: string;
}

export type TimelineEventType =
  | "CREATED" | "FIELD_CHANGE" | "NOTE" | "ARCHIVED" | "RESTORED";

export interface TimelineEvent {
  id: number;
  event_type: TimelineEventType;
  field_name: string | null;
  old_value: string | null;
  new_value: string | null;
  note_body: string | null;
  actor_name: string;
  created_at: string;
}

export interface MovementResult {
  movement: Movement;
  on_hand: Record<string, number>;
  on_hand_total: number;
}

export interface Assignment {
  id: number;
  user: number;
  location: number;
  location_code: string;
  assigned_by_name: string;
  assigned_at: string;
}

export interface Staff {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  assignments: Assignment[];
}

export interface WeeklyVolume {
  week: string;
  receipts: number;
  issues: number;
  movements: number;
}

export interface Breakdown {
  label: string;
  /** Only present on the location breakdown, where the label is a code. */
  name?: string;
  on_hand: number;
}

export interface DashboardData {
  active_items: number;
  low_stock_items: number;
  movements_today: number;
  items_moved_this_week: number;
  week_starts: string;
  total_on_hand: number;
  by_category: Breakdown[];
  by_location: Breakdown[];
  weekly: WeeklyVolume[];
  recent: Movement[];
}

export interface ImportRowError {
  row: number;
  sku: string;
  error: string;
}

/** Both imports report the same shape apart from their headline counters, so
 *  the optional fields distinguish them rather than two near-identical types. */
export interface ImportReport {
  created?: number;
  updated?: number;
  recorded?: number;
  failed: number;
  errors: ImportRowError[];
}
