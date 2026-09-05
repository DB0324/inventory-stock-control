import { api } from "./client";
import type {
  Account, Assignment, Category, DashboardData, ImportReport, Item, ItemInput,
  Location, NewAccount,
  Movement,
  MovementResult, Paginated,
  Staff, TimelineEvent,
} from "../types/api";

export const inventory = {
  categories: () => api.get<Paginated<Category>>("/api/categories/"),
  createCategory: (name: string) =>
    api.post<Category>("/api/categories/", { name }),
  renameCategory: (id: number, name: string) =>
    api.patch<Category>(`/api/categories/${id}/`, { name }),
  locations: () => api.get<Paginated<Location>>("/api/locations/"),

  accounts: () => api.get<Paginated<Account>>("/api/accounts/"),
  createAccount: (body: NewAccount) =>
    api.post<Account>("/api/accounts/", body),
  setAccountActive: (id: number, active: boolean) =>
    api.post<Account>(`/api/accounts/${id}/${active ? "reactivate" : "deactivate"}/`),

  items: (params: URLSearchParams) =>
    api.get<Paginated<Item>>(`/api/items/?${params}`),
  item: (id: number) => api.get<Item>(`/api/items/${id}/`),
  createItem: (body: ItemInput) => api.post<Item>("/api/items/", body),
  updateItem: (id: number, body: ItemInput) =>
    api.patch<Item>(`/api/items/${id}/`, body),
  archive: (id: number) => api.post<Item>(`/api/items/${id}/archive/`),
  restore: (id: number) => api.post<Item>(`/api/items/${id}/restore/`),

  movements: (id: number) =>
    api.get<Paginated<Movement>>(`/api/items/${id}/movements/`),
  timeline: (id: number) =>
    api.get<Paginated<TimelineEvent>>(`/api/items/${id}/timeline/`),
  addNote: (id: number, body: string) =>
    api.post<TimelineEvent>(`/api/items/${id}/notes/`, { body }),

  // Goal 10. The count is its own endpoint so the navigation badge, which is
  // on every screen, does not pull a serialized page of items each time.
  alerts: () => api.get<Paginated<Item>>("/api/alerts/"),
  alertCount: () => api.get<{ count: number }>("/api/alerts/count/"),
  dismissAlert: (id: number) => api.post<Item>(`/api/alerts/${id}/dismiss/`),

  // Goal 7. FormData, not JSON -- client.ts leaves the Content-Type alone
  // for FormData so the browser can set its own multipart boundary.
  importItems: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return api.post<ImportReport>("/api/imports/items/", body);
  },
  importReceipts: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return api.post<ImportReport>("/api/imports/receipts/", body);
  },

  // Goal 8. One request: the tiles are read together and each aggregate is
  // cheap, so six round trips on a cold instance would buy nothing.
  dashboard: () => api.get<DashboardData>("/api/dashboard/"),

  // Goal 5. Manager-only on the server; the UI just avoids offering it.
  staff: () => api.get<Paginated<Staff>>("/api/staff/"),
  assign: (user: number, location: number) =>
    api.post<Assignment>("/api/assignments/", { user, location }),
  unassign: (id: number) => api.delete<void>(`/api/assignments/${id}/`),

  receipt: (b: object) => api.post<MovementResult>("/api/movements/receipt/", b),
  issue: (b: object) => api.post<MovementResult>("/api/movements/issue/", b),
  adjustment: (b: object) => api.post<MovementResult>("/api/movements/adjustment/", b),
  transfer: (b: object) => api.post<MovementResult>("/api/movements/transfer/", b),
};