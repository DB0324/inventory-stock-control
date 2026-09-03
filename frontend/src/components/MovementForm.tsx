import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent, type ReactNode } from "react";

import { ApiError } from "../api/client";
import { inventory } from "../api/inventory";
import { useAuth } from "../auth/useAuth";
import type { Item, MovementKind } from "../types/api";

const KINDS: { kind: MovementKind; label: string; managerOnly: boolean }[] = [
  { kind: "RECEIPT", label: "Receipt", managerOnly: false },
  { kind: "ISSUE", label: "Issue", managerOnly: false },
  { kind: "TRANSFER", label: "Transfer", managerOnly: false },
  // Goal 1 lists adjustments as manager-only. The tab is absent for staff,
  // and the server returns 403 regardless -- this is convenience, not
  // enforcement.
  { kind: "ADJUSTMENT", label: "Adjustment", managerOnly: true },
];

export default function MovementForm({ item }: { item: Item }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const quantityRef = useRef<HTMLInputElement>(null);

  const [kind, setKind] = useState<MovementKind>("RECEIPT");
  const [location, setLocation] = useState("");
  const [source, setSource] = useState("");
  const [destination, setDestination] = useState("");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // Scoped by the server per role: every active location for a manager, only
  // assigned ones for staff. Staff cannot even select a location they would
  // be refused at, so the common case never produces an error at all.
  const locations = user?.locations ?? [];
  const tabs = KINDS.filter((k) => !k.managerOnly || user?.is_manager);
  const isTransfer = kind === "TRANSFER";
  const isAdjustment = kind === "ADJUSTMENT";

  const record = useMutation({
    mutationFn: (body: object) => {
      const fn = {
        RECEIPT: inventory.receipt,
        ISSUE: inventory.issue,
        TRANSFER: inventory.transfer,
        ADJUSTMENT: inventory.adjustment,
      }[kind];
      return fn(body);
    },
    onSuccess: (result) => {
      setError("");
      // The number comes from the server's SQL aggregate, not from adding the
      // quantity to what was on screen. Client-side arithmetic here is how
      // two screens start disagreeing.
      setSuccess(`Recorded. On hand is now ${result.on_hand_total}.`);
      setQuantity("");
      setReason("");
      setNote("");
      // Recording several movements in a row is the common case, so put the
      // cursor back where the next entry starts.
      quantityRef.current?.focus();
      queryClient.invalidateQueries({ queryKey: ["item", item.id] });
      queryClient.invalidateQueries({ queryKey: ["movements", item.id] });
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
    onError: (err) => {
      setSuccess("");
      // ApiError carries the server's own sentence, which for a 409 names the
      // actual quantities ("cannot issue 10, only 3 on hand"). Replacing that
      // with a generic message throws away the most useful thing it said.
      setError(
        err instanceof ApiError ? err.message : "Could not record the movement.",
      );
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");

    const base = { item: item.id, quantity: Number(quantity), note };
    const body = isTransfer
      ? { ...base, source: Number(source), destination: Number(destination) }
      : isAdjustment
        ? { ...base, location: Number(location), reason }
        : { ...base, location: Number(location) };

    record.mutate(body);
  }

  if (item.is_archived) {
    return (
      <div className="rounded-md border border-zinc-200 bg-zinc-50 p-4 text-sm text-zinc-500">
        This item is archived. Restore it to record new movements.
      </div>
    );
  }

  return (
    <div className="rounded-md border border-zinc-200 bg-white">
      <div className="flex gap-1 border-b border-zinc-200 px-2">
        {tabs.map((tab) => (
          <button
            key={tab.kind}
            type="button"
            onClick={() => {
              setKind(tab.kind);
              setError("");
              setSuccess("");
            }}
            className={`px-3 py-2 text-sm ${
              kind === tab.kind
                ? "border-b-2 border-accent-600 font-medium text-accent-700"
                : "text-zinc-500 hover:text-zinc-900"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* The adjustment form looks different on purpose. It is the only kind
          that admits the records were wrong, so it should feel deliberate
          rather than routine. */}
      {isAdjustment && (
        <div className="border-b border-amber-100 bg-amber-50 px-4 py-2 text-xs text-amber-800">
          An adjustment corrects a discrepancy. It needs a reason, and it stays
          in the ledger permanently.
        </div>
      )}

      <form onSubmit={submit} className="space-y-3 p-4">
        {error && (
          <div
            role="alert"
            className="rounded-sm bg-danger-50 px-3 py-2 text-sm text-danger-700"
          >
            {error}
          </div>
        )}
        {success && (
          <div className="rounded-sm bg-green-50 px-3 py-2 text-sm text-green-700">
            {success}
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {isTransfer ? (
            <>
              <Select
                label="From"
                value={source}
                onChange={setSource}
                options={locations}
              />
              <Select
                label="To"
                value={destination}
                onChange={setDestination}
                options={locations}
              />
            </>
          ) : (
            <Select
              label="Location"
              value={location}
              onChange={setLocation}
              options={locations}
            />
          )}

          <Field label={isAdjustment ? "Quantity (+/−)" : "Quantity"}>
            <input
              ref={quantityRef}
              type="number"
              required
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              className="w-full rounded-sm border border-zinc-300 px-3 py-1.5 text-sm tabular-nums focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
            />
          </Field>
        </div>

        {isAdjustment && (
          <Field label="Reason (required)">
            <input
              required
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Damaged in transit, cycle count variance…"
              className="w-full rounded-sm border border-zinc-300 px-3 py-1.5 text-sm focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
            />
          </Field>
        )}

        <Field label="Note (optional)">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="w-full rounded-sm border border-zinc-300 px-3 py-1.5 text-sm focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
          />
        </Field>

        <button
          type="submit"
          // Disabled while in flight, so an impatient double-click cannot
          // record the same receipt twice.
          disabled={record.isPending || locations.length === 0}
          className="rounded-md bg-accent-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-700 disabled:bg-zinc-300"
        >
          {record.isPending ? "Recording…" : `Record ${kind.toLowerCase()}`}
        </button>

        {locations.length === 0 && (
          <p className="text-xs text-zinc-500">
            You are not assigned to any location, so you cannot record
            movements. Ask a manager to assign you.
          </p>
        )}
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-zinc-600">{label}</span>
      {children}
    </label>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { id: number; code: string; name: string }[];
}) {
  return (
    <Field label={label}>
      <select
        required
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-sm border border-zinc-300 px-3 py-1.5 text-sm focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
      >
        <option value="">Select…</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.code} — {option.name}
          </option>
        ))}
      </select>
    </Field>
  );
}
