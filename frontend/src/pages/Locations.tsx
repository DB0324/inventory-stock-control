import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { inventory } from "../api/inventory";
import type { Staff } from "../types/api";

/** Goal 5's manager screen: who may record movements where.
 *
 * A grid of checkboxes rather than a form per person. The question a manager
 * actually has is "who can act at the shop floor?", which reads straight off
 * a column here and would need opening five pages in the other shape.
 *
 * Managers are absent by design -- they hold no assignment rows, because
 * their reach is universal by role. A row of permanently-ticked boxes would
 * imply an access model that does not exist, and worse, imply that unticking
 * one would do something.
 */
export default function Locations() {
  const queryClient = useQueryClient();

  const locations = useQuery({
    queryKey: ["locations"],
    queryFn: inventory.locations,
  });
  const staff = useQuery({ queryKey: ["staff"], queryFn: inventory.staff });

  const change = useMutation({
    mutationFn: async ({
      assignmentId,
      userId,
      locationId,
    }: {
      assignmentId?: number;
      userId: number;
      locationId: number;
    }) => {
      // Narrowed to void: one branch returns the new assignment and the other
      // returns nothing, and nothing downstream uses either. Letting the union
      // through would only push the noise into every caller.
      if (assignmentId) return inventory.unassign(assignmentId);
      await inventory.assign(userId, locationId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["staff"] });
      // A staff member's own /me/ payload carries their locations, so their
      // movement form dropdowns change with this.
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });

  function assignmentFor(person: Staff, locationId: number) {
    return person.assignments.find((a) => a.location === locationId);
  }

  if (locations.isLoading || staff.isLoading) {
    return <div className="text-sm text-zinc-500">Loading…</div>;
  }

  const error = locations.error ?? staff.error;
  if (error) {
    return (
      <div className="rounded-sm bg-danger-50 px-3 py-2 text-sm text-danger-700">
        <div className="font-medium">Could not load assignments.</div>
        <div className="mt-1 text-xs">
          {error instanceof ApiError
            ? `${error.status} — ${error.message}`
            : String(error)}
        </div>
      </div>
    );
  }

  const places = locations.data?.results ?? [];
  const people = staff.data?.results ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Locations and access</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Staff may only record movements at the locations ticked here.
          Managers are not listed: they can act everywhere by role, so there is
          nothing to grant or revoke.
        </p>
      </div>

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-zinc-700">Locations</h2>
        <div className="overflow-hidden rounded-md border border-zinc-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Code</th>
                <th className="px-3 py-2 text-left font-medium">Name</th>
                <th className="px-3 py-2 text-left font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {places.map((place) => (
                <tr key={place.id}>
                  <td className="px-3 py-2 font-mono text-xs">{place.code}</td>
                  <td className="px-3 py-2">{place.name}</td>
                  <td className="px-3 py-2 text-zinc-500">
                    {place.is_active ? "Active" : "Inactive"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-zinc-700">Staff access</h2>

        {people.length === 0 ? (
          <div className="rounded-md border border-zinc-200 bg-white p-8 text-center text-sm text-zinc-500">
            No staff accounts yet.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-md border border-zinc-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Staff member</th>
                  {places.map((place) => (
                    <th key={place.id} className="px-3 py-2 text-center font-medium">
                      {place.code}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {people.map((person) => (
                  <tr key={person.id}>
                    <td className="px-3 py-2">
                      <div>{person.full_name}</div>
                      <div className="text-xs text-zinc-500">{person.email}</div>
                    </td>
                    {places.map((place) => {
                      const assignment = assignmentFor(person, place.id);
                      return (
                        <td key={place.id} className="px-3 py-2 text-center">
                          <input
                            type="checkbox"
                            checked={Boolean(assignment)}
                            disabled={change.isPending}
                            onChange={() =>
                              change.mutate({
                                assignmentId: assignment?.id,
                                userId: person.id,
                                locationId: place.id,
                              })
                            }
                            aria-label={`${person.full_name} at ${place.code}`}
                            className="rounded-sm border-zinc-300"
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Who granted what, and when, is the reason this is a table with
            assigned_by rather than a many-to-many field. */}
        {people.some((p) => p.assignments.length > 0) && (
          <details className="text-xs text-zinc-500">
            <summary className="cursor-pointer">Who granted what</summary>
            <ul className="mt-2 space-y-1">
              {people.flatMap((person) =>
                person.assignments.map((a) => (
                  <li key={a.id}>
                    {person.full_name} at {a.location_code} — granted by{" "}
                    {a.assigned_by_name} on{" "}
                    {new Date(a.assigned_at).toLocaleDateString()}
                  </li>
                )),
              )}
            </ul>
          </details>
        )}
      </section>

      {change.error && (
        <div
          role="alert"
          className="rounded-sm bg-danger-50 px-3 py-2 text-sm text-danger-700"
        >
          {change.error instanceof ApiError
            ? change.error.message
            : "Could not change that assignment."}
        </div>
      )}
    </div>
  );
}
