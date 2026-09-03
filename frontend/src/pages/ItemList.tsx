import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { inventory } from "../api/inventory";
import ItemFilters from "../components/ItemFilters";
import { useAuth } from "../auth/useAuth";

export default function ItemList() {
  // Search state lives in the URL, not in useState. That makes a filtered
  // list linkable and survivable across a refresh, and it means the query key
  // below changes automatically when the filter does.
  const [params, setParams] = useSearchParams();
  const { user } = useAuth();

  const { data, isLoading, error } = useQuery({
    queryKey: ["items", params.toString()],
    queryFn: () => inventory.items(params),
  });

  const page = Number(params.get("page") ?? 1);
  const hasFilters = [...params.keys()].some((k) => k !== "page");

  function goToPage(next: number) {
    const params2 = new URLSearchParams(params);
    if (next <= 1) params2.delete("page");
    else params2.set("page", String(next));
    setParams(params2);
  }

  // A 404 from the list endpoint means "page past the end", not "broken".
  // A bookmarked or shared URL can point at page 4 of a result set that has
  // since shrunk, and an error page would be a lie about what went wrong.
  const pastEnd = error instanceof ApiError && error.status === 404;

  if (isLoading) {
    return <div className="text-sm text-zinc-500">Loading items…</div>;
  }
  if (error && !pastEnd) {
    // Say what actually went wrong. "Could not load items" is true of a 401,
    // a 500 and a dead network alike, and the three need different responses
    // from whoever is reading the screen.
    return (
      <div className="rounded-sm bg-danger-50 px-3 py-2 text-sm text-danger-700">
        <div className="font-medium">Could not load items.</div>
        <div className="mt-1 text-xs">
          {error instanceof ApiError
            ? `${error.status} — ${error.message}`
            : String(error)}
        </div>
      </div>
    );
  }

  const items = data?.results ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-semibold">Items</h1>
        <div className="flex items-baseline gap-4">
        {!pastEnd && (
          <span className="text-sm text-zinc-500">
            {data?.count ?? 0} {data?.count === 1 ? "item" : "items"}
          </span>
        )}
        {/* Managers only -- goal 2 says they create items. Staff record
            movements against items that already exist. */}
        {user?.is_manager && (
          <Link
            to="/items/new"
            className="rounded-md bg-accent-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-700"
          >
            New item
          </Link>
        )}
        </div>
      </div>

      <ItemFilters />

      {pastEnd ? (
        <div className="rounded-md border border-zinc-200 bg-white p-8 text-center text-sm text-zinc-500">
          <div>There are no results on page {page}.</div>
          <button
            type="button"
            onClick={() => goToPage(1)}
            className="mt-2 text-accent-700 underline hover:text-accent-600"
          >
            Back to the first page
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-md border border-zinc-200 bg-white p-8 text-center text-sm text-zinc-500">
          {/* Two very different situations, and telling someone "no items
              yet" when they have simply mistyped a search is unhelpful. */}
          {hasFilters ? "No items match these filters." : "No items yet."}
        </div>
      ) : (
        <div className="overflow-hidden rounded-md border border-zinc-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2 text-left font-medium">SKU</th>
                <th className="px-3 py-2 text-left font-medium">Name</th>
                <th className="px-3 py-2 text-left font-medium">Category</th>
                {/* Numbers right-aligned, always. A column of quantities is
                    unscannable otherwise -- you compare magnitudes by where
                    the digits end, and left alignment destroys that. */}
                <th className="px-3 py-2 text-right font-medium">On hand</th>
                <th className="px-3 py-2 text-right font-medium">Reorder</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {items.map((item) => {
                const low = item.on_hand <= item.reorder_level;
                return (
                  <tr key={item.id} className="hover:bg-zinc-50">
                    <td className="px-3 py-2 font-mono text-xs">
                      <Link
                        to={`/items/${item.id}`}
                        className="text-accent-700 hover:underline"
                      >
                        {item.sku}
                      </Link>
                    </td>
                    <td
                      className={`px-3 py-2 ${item.is_archived ? "text-zinc-400" : ""}`}
                    >
                      {item.name}
                      {item.is_archived && (
                        <span className="ml-2 text-xs text-zinc-400">
                          archived
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-zinc-600">
                      {item.category_name}
                    </td>
                    <td
                      className={`px-3 py-2 text-right tabular-nums ${
                        low ? "font-medium text-danger-700" : ""
                      }`}
                    >
                      {item.on_hand}
                      {/* Colour alone is not a signal. The screen reader gets
                          the same information the red text conveys. */}
                      {low && (
                        <span className="sr-only">
                          {" "}
                          (at or below reorder level)
                        </span>
                      )}
                      <span className="ml-1 text-xs text-zinc-400">
                        {item.unit_of_measure}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-zinc-500">
                      {item.reorder_level}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Prev/next rather than numbered pages: DRF gives us the two link
          fields directly, so this needs no arithmetic about how many pages
          exist and cannot drift out of step with the server's page size. */}
      {!pastEnd && (data?.next || data?.previous) && (
        <div className="flex items-center justify-between text-sm">
          <button
            type="button"
            onClick={() => goToPage(page - 1)}
            disabled={!data?.previous}
            className="rounded-md border border-zinc-300 px-3 py-1.5 hover:bg-white disabled:opacity-40"
          >
            ← Previous
          </button>
          <span className="text-zinc-500">Page {page}</span>
          <button
            type="button"
            onClick={() => goToPage(page + 1)}
            disabled={!data?.next}
            className="rounded-md border border-zinc-300 px-3 py-1.5 hover:bg-white disabled:opacity-40"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
