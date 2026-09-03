import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { inventory } from "../api/inventory";

/** Categories and locations change about once a month. Caching them for five
 *  minutes keeps a keystroke in the search box from refetching both. */
const REFERENCE_DATA_STALE_TIME = 5 * 60 * 1000;

const SORTS = [
  { value: "name", label: "Name (A–Z)" },
  { value: "-name", label: "Name (Z–A)" },
  { value: "sku", label: "SKU" },
  { value: "-on_hand", label: "On hand (high first)" },
  { value: "on_hand", label: "On hand (low first)" },
];

export default function ItemFilters() {
  const [params, setParams] = useSearchParams();

  // The search box is the one control that cannot write straight to the URL.
  // A round trip per keystroke would be a request per keystroke, so the input
  // holds its own value and pushes it to the URL once typing settles.
  const [term, setTerm] = useState(params.get("q") ?? "");

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: inventory.categories,
    staleTime: REFERENCE_DATA_STALE_TIME,
  });
  const locations = useQuery({
    queryKey: ["locations"],
    queryFn: inventory.locations,
    staleTime: REFERENCE_DATA_STALE_TIME,
  });

  /** Write one filter to the URL.
   *
   * Every change drops `page`. Without that, narrowing a filter while on
   * page 3 asks the server for page 3 of a result set that may now have one
   * page, and DRF answers 404. Resetting is the standard fix and it belongs
   * here, where the change originates, rather than in the list component.
   */
  function update(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("page");
    // replace, not push: otherwise Back walks through every intermediate
    // filter state instead of leaving the page.
    setParams(next, { replace: true });
  }

  // Debounce the search term into the URL. 300ms is long enough to skip the
  // middle of a word and short enough not to feel laggy.
  useEffect(() => {
    // Already in sync -- nothing to schedule. This is also what stops the
    // pair of effects here from ping-ponging off each other.
    if (term.trim() === (params.get("q") ?? "")) return;

    const timer = setTimeout(() => update("q", term.trim()), 300);
    return () => clearTimeout(timer);
    // `params` and `update` are intentionally excluded: including them
    // restarts the timer on every URL change, including the one this effect
    // just caused, so the search would never settle.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [term]);

  // Keep the box in step when the URL changes from elsewhere -- the Clear
  // button below, or the browser Back button.
  //
  // Adjusted during render rather than in an effect. React documents this as
  // the way to reset state when a prop changes: it re-renders immediately
  // with the new value instead of painting the stale one first and then
  // correcting it, and it avoids the cascading render an effect would cause.
  const urlTerm = params.get("q") ?? "";
  const [lastUrlTerm, setLastUrlTerm] = useState(urlTerm);
  if (urlTerm !== lastUrlTerm) {
    setLastUrlTerm(urlTerm);
    setTerm(urlTerm);
  }

  const hasFilters = ["q", "category", "location", "below_reorder", "archived", "sort"]
    .some((key) => params.get(key));

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-md border border-zinc-200 bg-white p-3">
      <label className="min-w-56 flex-1 space-y-1">
        <span className="text-xs font-medium text-zinc-600">Search</span>
        <input
          type="search"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          placeholder="Name or SKU…"
          className="w-full rounded-sm border border-zinc-300 px-3 py-1.5 text-sm focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
        />
      </label>

      <label className="space-y-1">
        <span className="text-xs font-medium text-zinc-600">Category</span>
        <select
          value={params.get("category") ?? ""}
          onChange={(e) => update("category", e.target.value)}
          className="rounded-sm border border-zinc-300 px-3 py-1.5 text-sm focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
        >
          <option value="">All</option>
          {categories.data?.results.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>

      <label className="space-y-1">
        <span className="text-xs font-medium text-zinc-600">Location</span>
        <select
          value={params.get("location") ?? ""}
          onChange={(e) => update("location", e.target.value)}
          className="rounded-sm border border-zinc-300 px-3 py-1.5 text-sm focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
        >
          <option value="">All (total on hand)</option>
          {locations.data?.results.map((l) => (
            <option key={l.id} value={l.id}>
              {l.code} — {l.name}
            </option>
          ))}
        </select>
      </label>

      <label className="space-y-1">
        <span className="text-xs font-medium text-zinc-600">Sort</span>
        <select
          value={params.get("sort") ?? "name"}
          onChange={(e) => update("sort", e.target.value === "name" ? "" : e.target.value)}
          className="rounded-sm border border-zinc-300 px-3 py-1.5 text-sm focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
        >
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-center gap-2 py-1.5 text-sm text-zinc-700">
        <input
          type="checkbox"
          checked={params.get("below_reorder") === "1"}
          onChange={(e) => update("below_reorder", e.target.checked ? "1" : "")}
          className="rounded-sm border-zinc-300"
        />
        Low stock only
      </label>

      <label className="flex items-center gap-2 py-1.5 text-sm text-zinc-700">
        <input
          type="checkbox"
          checked={params.get("archived") === "all"}
          onChange={(e) => update("archived", e.target.checked ? "all" : "")}
          className="rounded-sm border-zinc-300"
        />
        Include archived
      </label>

      {hasFilters && (
        <button
          type="button"
          onClick={() => setParams(new URLSearchParams(), { replace: true })}
          className="py-1.5 text-sm text-zinc-500 underline hover:text-zinc-900"
        >
          Clear
        </button>
      )}
    </div>
  );
}
