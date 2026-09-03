import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { inventory } from "../api/inventory";
import { useAuth } from "../auth/useAuth";
import MovementBadge from "../components/MovementBadge";
import MovementForm from "../components/MovementForm";
import Timeline from "../components/Timeline";

export default function ItemDetail() {
  const { id } = useParams();
  const itemId = Number(id);
  const [tab, setTab] = useState<"movements" | "history">("movements");
  const { user } = useAuth();
  const queryClient = useQueryClient();

  // Archive and restore are the same button with the label swapped -- they
  // are one toggle to the person using it, and pretending otherwise would
  // mean two mutations that can never both apply.
  const toggleArchive = useMutation({
    mutationFn: (archived: boolean) =>
      archived ? inventory.restore(itemId) : inventory.archive(itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["item", itemId] });
      queryClient.invalidateQueries({ queryKey: ["timeline", itemId] });
      queryClient.invalidateQueries({ queryKey: ["items"] });
      // Archived items drop out of the alerts list, so the badge moves too.
      queryClient.invalidateQueries({ queryKey: ["alert-count"] });
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });

  const item = useQuery({
    queryKey: ["item", itemId],
    queryFn: () => inventory.item(itemId),
  });

  // Kept as its own query rather than folded into the item request, so that
  // recording a movement can invalidate the two independently -- the header's
  // on-hand figure and the list below it refresh for different reasons.
  const movements = useQuery({
    queryKey: ["movements", itemId],
    queryFn: () => inventory.movements(itemId),
  });

  if (item.isLoading) {
    return <div className="text-sm text-zinc-500">Loading…</div>;
  }
  if (item.error || !item.data) {
    return (
      <div className="rounded-sm bg-danger-50 px-3 py-2 text-sm text-danger-700">
        Could not load this item.
      </div>
    );
  }

  const data = item.data;
  const low = data.on_hand <= data.reorder_level;

  return (
    <div className="space-y-6">
      <Link to="/items" className="text-sm text-zinc-500 hover:text-zinc-900">
        ← Items
      </Link>

      <div className="flex items-start justify-between rounded-md border border-zinc-200 bg-white p-4">
        <div>
          <div className="font-mono text-xs text-zinc-500">{data.sku}</div>
          <h1 className="text-xl font-semibold">{data.name}</h1>
          <div className="mt-1 text-sm text-zinc-500">
            {data.category_name} · reorder at {data.reorder_level}
            {data.is_archived && (
              <span className="ml-2 rounded-sm bg-zinc-100 px-1.5 py-0.5 text-xs">
                archived
              </span>
            )}
          </div>
        </div>
        <div className="flex items-start gap-6">
        {user?.is_manager && (
          <div className="flex gap-2">
            <Link
              to={`/items/${itemId}/edit`}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50"
            >
              Edit
            </Link>
            <button
              type="button"
              onClick={() => toggleArchive.mutate(data.is_archived)}
              disabled={toggleArchive.isPending}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 disabled:opacity-40"
            >
              {data.is_archived ? "Restore" : "Archive"}
            </button>
          </div>
        )}
        <div className="text-right">
          <div className="text-xs uppercase tracking-wide text-zinc-500">
            On hand
          </div>
          <div
            className={`text-3xl font-bold tabular-nums ${low ? "text-danger-700" : ""}`}
          >
            {data.on_hand}
          </div>
          <div className="text-xs text-zinc-400">{data.unit_of_measure}</div>
        </div>
        </div>
      </div>

      <MovementForm item={data} />

      <div>
        <div className="flex gap-1 border-b border-zinc-200">
          {(["movements", "history"] as const).map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => setTab(name)}
              className={`px-3 py-2 text-sm capitalize ${
                tab === name
                  ? "border-b-2 border-accent-600 font-medium text-accent-700"
                  : "text-zinc-500 hover:text-zinc-900"
              }`}
            >
              {name}
            </button>
          ))}
        </div>

        {tab === "movements" ? (
          <div className="mt-3 overflow-hidden rounded-md border border-zinc-200 bg-white">
            {movements.data?.results.length ? (
              <table className="w-full text-sm">
                <tbody className="divide-y divide-zinc-100">
                  {movements.data.results.map((m) => (
                    <tr key={m.id}>
                      <td className="px-3 py-2">
                        <MovementBadge kind={m.kind} />
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {m.quantity}
                      </td>
                      <td className="px-3 py-2 text-zinc-600">
                        {m.kind === "TRANSFER"
                          ? `${m.source_code} → ${m.destination_code}`
                          : m.location_code}
                      </td>
                      <td className="px-3 py-2 text-zinc-500">
                        {m.reason || m.note}
                      </td>
                      <td className="px-3 py-2 text-right text-xs text-zinc-400">
                        {m.recorded_by_name} ·{" "}
                        {new Date(m.recorded_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="p-6 text-center text-sm text-zinc-500">
                No movements recorded yet.
              </div>
            )}
          </div>
        ) : (
          <Timeline itemId={itemId} />
        )}
      </div>
    </div>
  );
}
