import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../api/client";
import { inventory } from "../api/inventory";
import type { Category, Staff } from "../types/api";

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

      <Categories />

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


/** Goal 2's other half: categories are "a short list that managers maintain".
 *
 * It lives on this page rather than getting its own nav entry because it is
 * the same kind of thing as the tables above -- a small reference list only a
 * manager touches -- and the navigation is already carrying six links.
 *
 * Add and rename, but no delete. Every item points at a category, so removing
 * one either orphans items or cascades into them, and neither is something a
 * stray click should be able to do. Renaming covers the real case (a typo, a
 * change of vocabulary) and, because items reference the row rather than the
 * text, it updates everywhere at once.
 */
function Categories() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: inventory.categories,
  });

  // One invalidation for both mutations. The item form's dropdown reads this
  // same query, so a category added here is selectable there without a reload.
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["categories"] });

  const add = useMutation({
    mutationFn: (value: string) => inventory.createCategory(value),
    onSuccess: () => {
      setName("");
      refresh();
    },
  });

  const rename = useMutation({
    mutationFn: ({ id, value }: { id: number; value: string }) =>
      inventory.renameCategory(id, value),
    onSuccess: refresh,
  });

  const rows = categories.data?.results ?? [];
  const error = add.error ?? rename.error;

  return (
    <section className="space-y-2">
      <h2 className="text-sm font-medium text-zinc-700">Categories</h2>

      <div className="rounded-md border border-zinc-200 bg-white">
        <ul className="divide-y divide-zinc-100">
          {rows.map((category) => (
            <CategoryRow
              key={category.id}
              category={category}
              busy={rename.isPending}
              onRename={(value) => rename.mutate({ id: category.id, value })}
            />
          ))}
          {rows.length === 0 && !categories.isLoading && (
            <li className="px-3 py-6 text-center text-sm text-zinc-500">
              No categories yet. Items need one, so add the first below.
            </li>
          )}
        </ul>

        <form
          className="flex gap-2 border-t border-zinc-100 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            const trimmed = name.trim();
            if (trimmed) add.mutate(trimmed);
          }}
        >
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="New category"
            aria-label="New category name"
            className="flex-1 rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
          />
          <button
            type="submit"
            disabled={!name.trim() || add.isPending}
            className="rounded-md bg-accent-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-700 disabled:bg-zinc-300"
          >
            {add.isPending ? "Adding…" : "Add"}
          </button>
        </form>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-sm bg-danger-50 px-3 py-2 text-sm text-danger-700"
        >
          {/* The common failure is a duplicate name, which the unique
              constraint turns into a 400 with a usable message. */}
          {error instanceof ApiError ? error.message : "Could not save that."}
        </div>
      )}
    </section>
  );
}

/** A row that edits in place.
 *
 * The draft lives here rather than in the parent so that typing in one row
 * does not re-render the whole list, and so there is no "which row am I
 * editing" state to keep in sync with the data.
 */
function CategoryRow({
  category,
  busy,
  onRename,
}: {
  category: Category;
  busy: boolean;
  onRename: (value: string) => void;
}) {
  const [draft, setDraft] = useState(category.name);

  // Commit on blur and on Enter, which is what an in-place edit is expected to
  // do. Guarded so that tabbing through the list without changing anything
  // does not fire a PATCH per row.
  function commit() {
    const trimmed = draft.trim();
    if (!trimmed) {
      setDraft(category.name);
      return;
    }
    if (trimmed !== category.name) onRename(trimmed);
  }

  return (
    <li className="flex items-center gap-3 px-3 py-2">
      <input
        value={draft}
        disabled={busy}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
          if (e.key === "Escape") setDraft(category.name);
        }}
        aria-label={`Rename ${category.name}`}
        className="flex-1 rounded-md border border-transparent px-2 py-1 text-sm hover:border-zinc-200 focus:border-zinc-300 focus:bg-white"
      />
      {!category.is_active && (
        <span className="text-xs text-zinc-500">Inactive</span>
      )}
    </li>
  );
}
