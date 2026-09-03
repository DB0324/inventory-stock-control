import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import { inventory } from "../api/inventory";
import MovementBadge from "../components/MovementBadge";
import WeeklyVolumeChart from "../components/WeeklyVolumeChart";
import type { Breakdown } from "../types/api";

export default function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: inventory.dashboard,
  });

  if (isLoading) {
    return <div className="text-sm text-zinc-500">Loading dashboard…</div>;
  }
  if (error || !data) {
    return (
      <div className="rounded-sm bg-danger-50 px-3 py-2 text-sm text-danger-700">
        <div className="font-medium">Could not load the dashboard.</div>
        <div className="mt-1 text-xs">
          {error instanceof ApiError
            ? `${error.status} — ${error.message}`
            : String(error)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Dashboard</h1>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label="Active items" value={data.active_items} />
        {/* The one tile that is a link, because it is the only one you can
            act on. Red because it is the number someone has to do something
            about, not merely observe. */}
        <Tile
          label="At or below reorder"
          value={data.low_stock_items}
          tone={data.low_stock_items > 0 ? "alert" : undefined}
          to="/alerts"
        />
        <Tile label="Movements today" value={data.movements_today} />
        <Tile label="Items moved this week" value={data.items_moved_this_week} />
      </div>

      <section className="rounded-md border border-zinc-200 bg-white p-4">
        <h2 className="mb-1 text-sm font-medium text-zinc-700">
          Received and issued, last eight weeks
        </h2>
        <p className="mb-3 text-xs text-zinc-500">
          Transfers and adjustments are excluded: a transfer moves stock without
          changing the total, and an adjustment is a correction rather than
          trade.
        </p>
        <WeeklyVolumeChart data={data.weekly} />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <BreakdownCard
          title="On hand by category"
          rows={data.by_category}
          total={data.total_on_hand}
        />
        <BreakdownCard
          title="On hand by location"
          rows={data.by_location}
          total={data.total_on_hand}
        />
      </div>

      <section className="rounded-md border border-zinc-200 bg-white">
        <h2 className="border-b border-zinc-100 px-4 py-2 text-sm font-medium text-zinc-700">
          Recent activity
        </h2>
        {data.recent.length === 0 ? (
          <p className="p-6 text-center text-sm text-zinc-500">
            Nothing recorded yet.
          </p>
        ) : (
          <table className="w-full text-sm">
            <tbody className="divide-y divide-zinc-100">
              {data.recent.map((movement) => (
                <tr key={movement.id}>
                  <td className="px-4 py-2">
                    <MovementBadge kind={movement.kind} />
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {movement.quantity}
                  </td>
                  <td className="px-2 py-2 text-zinc-600">
                    {movement.kind === "TRANSFER"
                      ? `${movement.source_code} → ${movement.destination_code}`
                      : movement.location_code}
                  </td>
                  <td className="px-2 py-2 text-right text-xs text-zinc-400">
                    {movement.recorded_by_name} ·{" "}
                    {new Date(movement.recorded_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function Tile({
  label,
  value,
  tone,
  to,
}: {
  label: string;
  value: number;
  tone?: "alert";
  to?: string;
}) {
  const body = (
    <>
      <div className="text-xs uppercase tracking-wide text-zinc-500">{label}</div>
      <div
        className={`mt-1 text-3xl font-bold tabular-nums ${
          tone === "alert" ? "text-danger-700" : "text-zinc-900"
        }`}
      >
        {value}
      </div>
    </>
  );

  const className =
    "block rounded-md border border-zinc-200 bg-white p-4" +
    (to ? " hover:border-zinc-300" : "");

  return to ? (
    <Link to={to} className={className}>
      {body}
    </Link>
  ) : (
    <div className={className}>{body}</div>
  );
}

/** A breakdown as labelled bars rather than a pie.
 *
 * Pies make people compare angles, which they are bad at; a bar makes them
 * compare lengths against a shared baseline, which they are good at. The
 * number is printed too, so nothing depends on reading the bar precisely. */
function BreakdownCard({
  title,
  rows,
  total,
}: {
  title: string;
  rows: Breakdown[];
  total: number;
}) {
  const peak = Math.max(1, ...rows.map((row) => row.on_hand));

  return (
    <section className="rounded-md border border-zinc-200 bg-white p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-medium text-zinc-700">{title}</h2>
        <span className="text-xs text-zinc-500 tabular-nums">
          {total} total
        </span>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-zinc-500">Nothing to show yet.</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => (
            <li key={row.label} className="text-sm">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate text-zinc-700">
                  {row.label}
                  {row.name && (
                    <span className="ml-1 text-xs text-zinc-400">{row.name}</span>
                  )}
                </span>
                <span className="tabular-nums text-zinc-600">{row.on_hand}</span>
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-zinc-100">
                <div
                  className="h-1.5 rounded-full bg-accent-600"
                  style={{ width: `${(row.on_hand / peak) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
