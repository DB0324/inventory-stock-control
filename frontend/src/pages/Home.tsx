import { useAuth } from "../auth/useAuth";

/** Placeholder. Its job right now is to prove the session survived the
 *  redirect and that /me/ returned the role and locations the UI will later
 *  be built on. */
export default function Home() {
  const { user, logout } = useAuth();

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold">Signed in</h1>
      <dl className="mt-4 space-y-1 text-sm">
        <div>
          {user?.full_name} — {user?.email}
        </div>
        <div>Role: {user?.role}</div>
        <div>
          Locations: {user?.locations.map((l) => l.code).join(", ") || "none"}
        </div>
      </dl>
      <button
        onClick={logout}
        className="mt-6 rounded-md border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50"
      >
        Sign out
      </button>
    </div>
  );
}
