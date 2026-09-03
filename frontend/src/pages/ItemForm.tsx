import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { inventory } from "../api/inventory";
import type { Item } from "../types/api";

/** Create and edit share one component because the fields are identical and
 *  the only differences are the heading, the endpoint, and whether the SKU can
 *  still be changed. Two components would be the same form twice. */
export default function ItemForm() {
  const { id } = useParams();
  const isEdit = id !== undefined;
  const itemId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [fields, setFields] = useState({
    sku: "",
    name: "",
    description: "",
    unit_of_measure: "EA",
    reorder_level: "0",
    category: "",
  });
  // Per-field messages from DRF, keyed by field name, so a bad value is shown
  // against the input that caused it rather than as a banner at the top.
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [formError, setFormError] = useState("");
  const [loaded, setLoaded] = useState(!isEdit);

  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: inventory.categories,
  });

  const existing = useQuery({
    queryKey: ["item", itemId],
    queryFn: () => inventory.item(itemId),
    enabled: isEdit,
  });

  // Populate once, when the item arrives. Adjusted during render rather than
  // in an effect: an effect would paint the empty form first and then correct
  // it, and `loaded` is what stops it clobbering what the user has typed.
  if (isEdit && !loaded && existing.data) {
    const item = existing.data;
    setFields({
      sku: item.sku,
      name: item.name,
      description: item.description,
      unit_of_measure: item.unit_of_measure,
      reorder_level: String(item.reorder_level),
      category: String(item.category),
    });
    setLoaded(true);
  }

  const save = useMutation({
    mutationFn: (body: Partial<Item>) =>
      isEdit ? inventory.updateItem(itemId, body) : inventory.createItem(body),
    onSuccess: (item) => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
      queryClient.invalidateQueries({ queryKey: ["item", item.id] });
      // The timeline gains a CREATED or FIELD_CHANGE event either way.
      queryClient.invalidateQueries({ queryKey: ["timeline", item.id] });
      queryClient.invalidateQueries({ queryKey: ["alert-count"] });
      navigate(`/items/${item.id}`);
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        setErrors(error.fields ?? {});
        // A field-level error is already shown beside its input, so only put
        // something at the top when there is nothing else to see.
        setFormError(error.fields ? "" : error.message);
      } else {
        setFormError("Could not reach the server.");
      }
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setErrors({});
    setFormError("");
    save.mutate({
      sku: fields.sku,
      name: fields.name,
      description: fields.description,
      unit_of_measure: fields.unit_of_measure,
      reorder_level: Number(fields.reorder_level),
      category: Number(fields.category),
    });
  }

  function set(key: keyof typeof fields, value: string) {
    setFields((previous) => ({ ...previous, [key]: value }));
  }

  if (isEdit && existing.isLoading) {
    return <div className="text-sm text-zinc-500">Loading…</div>;
  }

  return (
    <div className="max-w-2xl space-y-4">
      <h1 className="text-xl font-semibold">
        {isEdit ? `Edit ${existing.data?.sku ?? ""}` : "New item"}
      </h1>

      <form
        onSubmit={submit}
        className="space-y-4 rounded-md border border-zinc-200 bg-white p-4"
      >
        {formError && (
          <div
            role="alert"
            className="rounded-sm bg-danger-50 px-3 py-2 text-sm text-danger-700"
          >
            {formError}
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="SKU" errors={errors.sku}>
            <input
              required
              value={fields.sku}
              onChange={(e) => set("sku", e.target.value)}
              // Uppercased on save by Item.save(), and unique
              // case-insensitively at the database. Showing it uppercase here
              // means what you type matches what gets stored.
              className="w-full rounded-sm border border-zinc-300 px-3 py-1.5 font-mono text-sm uppercase focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
            />
          </Field>

          <Field label="Category" errors={errors.category}>
            <select
              required
              value={fields.category}
              onChange={(e) => set("category", e.target.value)}
              className="w-full rounded-sm border border-zinc-300 px-3 py-1.5 text-sm focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
            >
              <option value="">Select…</option>
              {categories.data?.results.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="Name" errors={errors.name}>
          <input
            required
            value={fields.name}
            onChange={(e) => set("name", e.target.value)}
            className="w-full rounded-sm border border-zinc-300 px-3 py-1.5 text-sm focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
          />
        </Field>

        <Field label="Description" errors={errors.description}>
          <textarea
            rows={3}
            value={fields.description}
            onChange={(e) => set("description", e.target.value)}
            className="w-full rounded-sm border border-zinc-300 px-3 py-1.5 text-sm focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Unit of measure" errors={errors.unit_of_measure}>
            <input
              required
              value={fields.unit_of_measure}
              onChange={(e) => set("unit_of_measure", e.target.value)}
              placeholder="EA, BOX, ROLL…"
              className="w-full rounded-sm border border-zinc-300 px-3 py-1.5 text-sm focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
            />
          </Field>

          <Field label="Reorder level" errors={errors.reorder_level}>
            <input
              type="number"
              min={0}
              required
              value={fields.reorder_level}
              onChange={(e) => set("reorder_level", e.target.value)}
              className="w-full rounded-sm border border-zinc-300 px-3 py-1.5 text-sm tabular-nums focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
            />
          </Field>
        </div>

        <div className="flex gap-2 pt-2">
          <button
            type="submit"
            disabled={save.isPending}
            className="rounded-md bg-accent-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-700 disabled:bg-zinc-300"
          >
            {save.isPending ? "Saving…" : isEdit ? "Save changes" : "Create item"}
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="rounded-md border border-zinc-300 px-4 py-1.5 text-sm hover:bg-zinc-50"
          >
            Cancel
          </button>
        </div>

        {isEdit && (
          <p className="text-xs text-zinc-500">
            Every change is recorded in this item's history with the old and
            new value, and cannot be edited afterwards.
          </p>
        )}
      </form>
    </div>
  );
}

function Field({
  label,
  errors,
  children,
}: {
  label: string;
  errors?: string[];
  children: ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-zinc-600">{label}</span>
      {children}
      {errors?.map((message) => (
        <span key={message} className="block text-xs text-danger-700">
          {message}
        </span>
      ))}
    </label>
  );
}
