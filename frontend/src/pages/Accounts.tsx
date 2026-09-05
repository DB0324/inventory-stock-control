import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError } from "../api/client";
import { inventory } from "../api/inventory";
import { useAuth } from "../auth/useAuth";
import type { Account, Role } from "../types/api";

/** Manager-only account administration.
 *
 * The sign-in page has no "create an account" link and that is deliberate. In
 * an inventory system the user list is the permissions list: any account, even
 * a brand new one with no locations assigned, can read the entire catalogue
 * and every stock position. So accounts are created here, by the same person
 * who already decides who may act where.
 *
 * Accounts are deactivated, never deleted. Movements point at the person who
 * recorded them, and a ledger entry with no author is worse than no ledger.
 */
export default function Accounts() {
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const accounts = useQuery({
    queryKey: ["accounts"],
    queryFn: inventory.accounts,
  });

  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      inventory.setAccountActive(id, active),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["accounts"] }),
  });

  const rows = accounts.data?.results ?? [];

  if (accounts.isLoading) {
    return <div className="text-sm text-zinc-500">Loading…</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">People</h1>
        <p className="mt-1 text-sm text-zinc-500">
          There is no public sign-up. An account can read every stock position
          the business holds, so a manager creates each one here. Access is
          withdrawn by deactivating, which leaves the person&rsquo;s recorded
          movements intact and still attributed to them.
        </p>
      </div>

      <NewAccountForm />

      <section className="space-y-2">
        <h2 className="text-sm font-medium text-zinc-700">Accounts</h2>
        <div className="overflow-x-auto rounded-md border border-zinc-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Name</th>
                <th className="px-3 py-2 text-left font-medium">Role</th>
                <th className="px-3 py-2 text-left font-medium">Status</th>
                <th className="px-3 py-2 text-right font-medium">Access</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {rows.map((account) => (
                <AccountRow
                  key={account.id}
                  account={account}
                  isSelf={account.id === user?.id}
                  busy={toggle.isPending}
                  onToggle={() =>
                    toggle.mutate({
                      id: account.id,
                      active: !account.is_active,
                    })
                  }
                />
              ))}
            </tbody>
          </table>
        </div>

        {toggle.error && (
          <div
            role="alert"
            className="rounded-sm bg-danger-50 px-3 py-2 text-sm text-danger-700"
          >
            {toggle.error instanceof ApiError
              ? toggle.error.message
              : "Could not change that account."}
          </div>
        )}
      </section>
    </div>
  );
}

function AccountRow({
  account,
  isSelf,
  busy,
  onToggle,
}: {
  account: Account;
  isSelf: boolean;
  busy: boolean;
  onToggle: () => void;
}) {
  return (
    <tr className={account.is_active ? "" : "bg-zinc-50 text-zinc-500"}>
      <td className="px-3 py-2">
        <div>{account.full_name}</div>
        <div className="text-xs text-zinc-500">{account.email}</div>
      </td>
      <td className="px-3 py-2">
        <span className="rounded-sm bg-zinc-100 px-1.5 py-0.5 text-xs font-medium text-zinc-600">
          {account.role}
        </span>
      </td>
      <td className="px-3 py-2">
        {account.is_active ? "Active" : "No access"}
      </td>
      <td className="px-3 py-2 text-right">
        {isSelf ? (
          /* The server refuses this too. Showing why is friendlier than a
             button that always returns 400, and the guard that matters is
             still the one on the server. */
          <span className="text-xs text-zinc-400">This is you</span>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={onToggle}
            className="rounded-md border border-zinc-300 px-3 py-1 text-xs font-medium hover:bg-zinc-50 disabled:opacity-50"
          >
            {account.is_active ? "Revoke access" : "Restore access"}
          </button>
        )}
      </td>
    </tr>
  );
}

function NewAccountForm() {
  const queryClient = useQueryClient();
  const [fields, setFields] = useState({
    full_name: "",
    email: "",
    role: "STAFF" as Role,
    password: "",
  });
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const [done, setDone] = useState("");

  const create = useMutation({
    mutationFn: () => inventory.createAccount(fields),
    onSuccess: (account) => {
      queryClient.invalidateQueries({ queryKey: ["accounts"] });
      // The assignment grid reads a different endpoint, and a new staff
      // member needs to appear there to be given any locations.
      queryClient.invalidateQueries({ queryKey: ["staff"] });
      setDone(`${account.full_name} can now sign in as ${account.email}.`);
      setFields({ full_name: "", email: "", role: "STAFF", password: "" });
    },
    onError: (error) => {
      setErrors(error instanceof ApiError ? (error.fields ?? {}) : {});
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setErrors({});
    setDone("");
    create.mutate();
  }

  function set(key: keyof typeof fields, value: string) {
    setFields((previous) => ({ ...previous, [key]: value }));
  }

  return (
    <section className="rounded-md border border-zinc-200 bg-white p-4">
      <h2 className="text-sm font-medium text-zinc-700">Add someone</h2>
      <form onSubmit={submit} className="mt-3 space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Full name" errors={errors.full_name}>
            <input
              value={fields.full_name}
              onChange={(e) => set("full_name", e.target.value)}
              required
              className="w-full rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
            />
          </Field>

          <Field label="Email" errors={errors.email}>
            <input
              type="email"
              value={fields.email}
              onChange={(e) => set("email", e.target.value)}
              required
              className="w-full rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
            />
          </Field>

          <Field label="Role" errors={errors.role}>
            <select
              value={fields.role}
              onChange={(e) => set("role", e.target.value)}
              className="w-full rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
            >
              <option value="STAFF">Warehouse staff</option>
              <option value="MANAGER">Inventory manager</option>
            </select>
          </Field>

          <Field label="Initial password" errors={errors.password}>
            <input
              type="password"
              value={fields.password}
              onChange={(e) => set("password", e.target.value)}
              required
              autoComplete="new-password"
              className="w-full rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
            />
          </Field>
        </div>

        <p className="text-xs text-zinc-500">
          {/* Being straight about the limitation rather than implying this is
              how it should work in production. */}
          Set a password and pass it on. A production deployment would email a
          single-use invitation link instead, so the password never travels
          through a third party.
        </p>

        <button
          type="submit"
          disabled={create.isPending}
          className="rounded-md bg-accent-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-700 disabled:bg-zinc-300"
        >
          {create.isPending ? "Creating…" : "Create account"}
        </button>
      </form>

      {done && (
        <div className="mt-3 rounded-sm bg-zinc-50 px-3 py-2 text-sm text-zinc-700">
          {done}
        </div>
      )}

      {create.error && !Object.keys(errors).length && (
        <div
          role="alert"
          className="mt-3 rounded-sm bg-danger-50 px-3 py-2 text-sm text-danger-700"
        >
          {create.error instanceof ApiError
            ? create.error.message
            : "Could not create that account."}
        </div>
      )}
    </section>
  );
}

function Field({
  label,
  errors,
  children,
}: {
  label: string;
  errors?: string[];
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-zinc-600">
        {label}
      </span>
      {children}
      {errors?.map((message) => (
        <span key={message} className="mt-1 block text-xs text-danger-700">
          {message}
        </span>
      ))}
    </label>
  );
}
