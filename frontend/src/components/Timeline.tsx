import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { inventory } from "../api/inventory";
import type { TimelineEvent } from "../types/api";

/** One sentence per event type. Kept as a function rather than a map because
 *  each shape reads from different fields, and a lookup table would end up
 *  passing every field to every renderer anyway. */
function describe(event: TimelineEvent) {
  switch (event.event_type) {
    case "CREATED":
      return <span>created this item</span>;
    case "ARCHIVED":
      return <span>archived this item</span>;
    case "RESTORED":
      return <span>restored this item</span>;
    case "NOTE":
      return <span className="text-zinc-800">{event.note_body}</span>;
    case "FIELD_CHANGE":
      return (
        <span>
          changed <span className="font-medium">{event.field_name}</span> from{" "}
          <span className="text-zinc-500 line-through">{event.old_value}</span>{" "}
          to <span className="font-medium">{event.new_value}</span>
        </span>
      );
  }
}

export default function Timeline({ itemId }: { itemId: number }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");

  const { data } = useQuery({
    queryKey: ["timeline", itemId],
    queryFn: () => inventory.timeline(itemId),
  });

  const addNote = useMutation({
    mutationFn: (body: string) => inventory.addNote(itemId, body),
    onSuccess: () => {
      setNote("");
      // Refetch rather than push the new event into the cache by hand. The
      // server decides the ordering and the actor name; guessing them here
      // would show something subtly different from what was stored.
      queryClient.invalidateQueries({ queryKey: ["timeline", itemId] });
    },
  });

  return (
    <div className="mt-3 space-y-3">
      <div className="flex gap-2">
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Add a note…"
          className="flex-1 rounded-sm border border-zinc-300 px-3 py-1.5 text-sm focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
        />
        <button
          onClick={() => note.trim() && addNote.mutate(note)}
          disabled={!note.trim() || addNote.isPending}
          className="rounded-md bg-accent-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-700 disabled:bg-zinc-300"
        >
          Add
        </button>
      </div>

      {/* No edit or delete control anywhere in here, for any role. Their
          absence is goal 9 made visible -- and the banner says so out loud,
          because a missing button is easy to read as an oversight. */}
      <div className="rounded-md border border-zinc-200 bg-white">
        <div className="flex items-center gap-1.5 border-b border-zinc-100 px-3 py-2 text-xs text-zinc-500">
          <span aria-hidden>🔒</span> History cannot be edited
        </div>
        <ol className="divide-y divide-zinc-100">
          {data?.results.map((event) => (
            <li key={event.id} className="px-3 py-2 text-sm">
              <span className="font-medium">{event.actor_name}</span>{" "}
              {describe(event)}
              <time
                dateTime={event.created_at}
                className="ml-2 text-xs text-zinc-400"
              >
                {new Date(event.created_at).toLocaleString()}
              </time>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
