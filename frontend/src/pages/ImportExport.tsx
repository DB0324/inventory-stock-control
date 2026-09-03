import { useMutation } from "@tanstack/react-query";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../api/client";
import { inventory } from "../api/inventory";
import type { ImportReport } from "../types/api";

const ITEM_COLUMNS = "sku, name, category, unit_of_measure, reorder_level, description";
const RECEIPT_COLUMNS = "sku, location, quantity, note";

export default function ImportExport() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Import and export</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Every valid row is imported even if others fail. Failures are listed
          by line number so they can be fixed in the original file.
        </p>
      </div>

      <ImportCard
        title="Items"
        columns={ITEM_COLUMNS}
        note="A row whose SKU already exists updates that item rather than creating a second one. Categories must already exist."
        upload={inventory.importItems}
      />

      <ImportCard
        title="Stock receipts"
        columns={RECEIPT_COLUMNS}
        note="Recorded through the same rules as the movement form: archived items are refused, and every receipt lands in the ledger."
        upload={inventory.importReceipts}
      />

      <section className="rounded-md border border-zinc-200 bg-white p-4">
        <h2 className="text-sm font-medium text-zinc-700">
          Export the current stock position
        </h2>
        <p className="mt-1 mb-3 text-sm text-zinc-500">
          Every item&rsquo;s on-hand quantity, split by location, as it stands
          right now.
        </p>
        {/* A plain link, not a fetch. The browser downloads it directly, the
            session cookie rides along, and nothing has to be held in memory
            to hand it back. */}
        <a
          href={`${import.meta.env.VITE_API_URL ?? ""}/api/exports/stock-position/`}
          className="inline-block rounded-md bg-accent-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-700"
        >
          Download CSV
        </a>
      </section>
    </div>
  );
}

function ImportCard({
  title,
  columns,
  note,
  upload,
}: {
  title: string;
  columns: string;
  note: string;
  upload: (file: File) => Promise<ImportReport>;
}) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);

  const run = useMutation({
    mutationFn: (chosen: File) => upload(chosen),
    onSuccess: () => {
      // An import can touch almost everything, so this is deliberately broad
      // rather than a careful list that would go stale as pages are added.
      queryClient.invalidateQueries();
    },
  });

  const report = run.data;

  return (
    <section className="rounded-md border border-zinc-200 bg-white p-4">
      <h2 className="text-sm font-medium text-zinc-700">{title}</h2>
      <p className="mt-1 text-sm text-zinc-500">{note}</p>
      <p className="mt-1 text-xs text-zinc-500">
        Columns: <code className="font-mono">{columns}</code>
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            run.reset();
          }}
          className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-sm"
        />
        <button
          type="button"
          disabled={!file || run.isPending}
          onClick={() => file && run.mutate(file)}
          className="rounded-md bg-accent-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-700 disabled:bg-zinc-300"
        >
          {run.isPending ? "Importing…" : "Import"}
        </button>
      </div>

      {run.error && (
        <div
          role="alert"
          className="mt-3 rounded-sm bg-danger-50 px-3 py-2 text-sm text-danger-700"
        >
          {/* A 400 here means the file itself was unusable -- a missing
              column, not valid UTF-8 -- which is a different answer from
              "some rows failed" and reads differently on purpose. */}
          {run.error instanceof ApiError
            ? run.error.message
            : "Could not upload that file."}
        </div>
      )}

      {report && (
        <div className="mt-3 space-y-2">
          <div className="rounded-sm bg-zinc-50 px-3 py-2 text-sm">
            {"created" in report && (
              <span className="mr-4 tabular-nums">
                {report.created} created, {report.updated} updated
              </span>
            )}
            {"recorded" in report && (
              <span className="mr-4 tabular-nums">
                {report.recorded} receipts recorded
              </span>
            )}
            <span
              className={`tabular-nums ${
                report.failed > 0 ? "font-medium text-danger-700" : "text-zinc-500"
              }`}
            >
              {report.failed} failed
            </span>
          </div>

          {report.errors.length > 0 && (
            <div className="overflow-hidden rounded-md border border-danger-600/20">
              <table className="w-full text-sm">
                <thead className="bg-danger-50 text-xs uppercase tracking-wide text-danger-700">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Line</th>
                    <th className="px-3 py-2 text-left font-medium">SKU</th>
                    <th className="px-3 py-2 text-left font-medium">Why it failed</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {report.errors.map((row) => (
                    <tr key={`${row.row}-${row.sku}`}>
                      {/* The line number as the spreadsheet counts it, so it
                          can be found without arithmetic. */}
                      <td className="px-3 py-2 tabular-nums">{row.row}</td>
                      <td className="px-3 py-2 font-mono text-xs">{row.sku}</td>
                      <td className="px-3 py-2 text-zinc-700">{row.error}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
