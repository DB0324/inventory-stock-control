import { api } from "./client";
import type {
  Category, Item, Movement, MovementResult, Paginated, TimelineEvent,
} from "../types/api";

export const inventory = {
  categories: () => api.get<Paginated<Category>>("/api/categories/"),
  locations: () => api.get<Paginated<{ id: number; code: string; name: string }>>(
    "/api/locations/"),

  items: (params: URLSearchParams) =>
    api.get<Paginated<Item>>(`/api/items/?${params}`),
  item: (id: number) => api.get<Item>(`/api/items/${id}/`),
  createItem: (body: Partial<Item>) => api.post<Item>("/api/items/", body),
  updateItem: (id: number, body: Partial<Item>) =>
    api.patch<Item>(`/api/items/${id}/`, body),
  archive: (id: number) => api.post<Item>(`/api/items/${id}/archive/`),
  restore: (id: number) => api.post<Item>(`/api/items/${id}/restore/`),

  movements: (id: number) =>
    api.get<Paginated<Movement>>(`/api/items/${id}/movements/`),
  timeline: (id: number) =>
    api.get<Paginated<TimelineEvent>>(`/api/items/${id}/timeline/`),
  addNote: (id: number, body: string) =>
    api.post<TimelineEvent>(`/api/items/${id}/notes/`, { body }),

  receipt: (b: object) => api.post<MovementResult>("/api/movements/receipt/", b),
  issue: (b: object) => api.post<MovementResult>("/api/movements/issue/", b),
  adjustment: (b: object) => api.post<MovementResult>("/api/movements/adjustment/", b),
  transfer: (b: object) => api.post<MovementResult>("/api/movements/transfer/", b),
};