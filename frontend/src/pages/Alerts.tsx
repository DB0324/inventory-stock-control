import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import { inventory } from "../api/inventory";
import { useAuth } from "../auth/useAuth";

export default function Alerts() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["alerts"],
    queryFn: inventory.alerts,
  });

  const dismiss = useMutation({
    mutationFn: (id: number) => inventory.dismissAlert(id),
    onSuccess: () => {
      // Both the list and the badge. Refetching rather than removing the row
      // by hand, because the server decides what still qualifies -- and
      // dismissing one item can never change another, but the badge count is
      // the server's number and should stay the server's number.
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["alert-count"] });
    },
  });

  if (isLoading) {
    return <div className="text-sm text-zinc-500">Loading alerts…</div>;
  }
  if (error) {
    return (
      <div className="rounded-sm bg-danger-50 px-3 py-2 text-sm text-danger-700">
        <div className="font-medium">Could not load alerts.</div>
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
        <h1 className="text-xl font-semibold">Low stock</h1>
        <span className="text-sm text-zinc-500">
          {data?.count ?? 0} {data?.count === 1 ? "item" : "items"}
        </span>
      </div>

      <p className="text-sm text-zinc-500">
        Items at or below their reorder level, counting stock across every
        location. Dismissing one hides it until the item is restocked above
        its reorder level and falls back again.
      </p>

      {items.length === 0 ? (
        <div className="rounded-md border border-zinc-200 bg-white p-8 text-center text-sm text-zinc-500">
          Nothing is low on stock.
        </div>
      ) : (
        <div className="overflow-hidden rounded-md border border-zinc-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2 text-left font-medium">SKU</th>
                <th className="px-3 py-2 text-left font-medium">Name</th>
                <th className="px-3 py-2 text-left font-medium">Category</th>
                <th className="px-3 py-2 text-right font-medium">On hand</th>
                <th className="px-3 py-2 text-right font-medium">Reorder</th>
                <th className="px-3 py-2 text-right font-medium">Short by</th>
                {/* The column is absent for staff rather than disabled.
                    A disabled button invites someone to wonder what they did
                    wrong; the server returns 403 either way. */}
                {user?.is_manager && <th className="px-3 py-2" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {items.map((item) => (
                <tr key={item.id} className="hover:bg-zinc-50">
                  <td className="px-3 py-2 font-mono text-xs">
                    <Link
                      to={`/items/${item.id}`}
                      className="text-accent-700 hover:underline"
                    >
                      {item.sku}
                    </Link>
                  </td>
                  <td className="px-3 py-2">{item.name}</td>
                  <td className="px-3 py-2 text-zinc-600">
                    {item.category_name}
                  </td>
                  <td className="px-3 py-2 text-right font-medium tabular-nums text-danger-700">
                    {item.on_hand}
                    <span className="ml-1 text-xs font-normal text-zinc-400">
                      {item.unit_of_measure}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-zinc-500">
                    {item.reorder_level}
                  </td>
                  {/* The number someone actually needs in order to act: how
                      much to order, not two figures to subtract in their head. */}
                  <td className="px-3 py-2 text-right tabular-nums">
                    {item.reorder_level - item.on_hand}
                  </td>
                  {user?.is_manager && (
                    <td className="px-3 py-2 text-right">
                      <button
                        type="button"
                        onClick={() => dismiss.mutate(item.id)}
                        disabled={dismiss.isPending}
                        className="rounded-md border border-zinc-300 px-2 py-1 text-xs hover:bg-zinc-50 disabled:opacity-40"
                      >
                        Dismiss
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {dismiss.error && (
        <div
          role="alert"
          className="rounded-sm bg-danger-50 px-3 py-2 text-sm text-danger-700"
        >
          {dismiss.error instanceof ApiError
            ? dismiss.error.message
            : "Could not dismiss that alert."}
        </div>
      )}
    </div>
  );
}
