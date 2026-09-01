export type Role = "MANAGER" | "STAFF";

export interface LocationBrief {
  id: number;
  code: string;
  name: string;
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
