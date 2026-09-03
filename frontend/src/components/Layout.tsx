import { Link, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../auth/useAuth";

export default function Layout() {
  const { user, logout, loggingOut } = useAuth();
  const { pathname } = useLocation();

  // Only Items for now. The Locations link comes back with goal 5, when
  // there's a page behind it -- a dead link visible only to managers is
  // worse than a missing one, since managers are who reviews this.
  const links = [{ to: "/", label: "Items" }];

  return (
    <div className="min-h-screen bg-zinc-50">
      <header className="border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3">
          <span className="font-semibold">Inventory</span>
          <nav className="flex gap-4 text-sm">
            {links.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={
                  pathname === link.to
                    ? "font-medium text-accent-700"
                    : "text-zinc-600 hover:text-zinc-900"
                }
              >
                {link.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm text-zinc-500">
            <span>{user?.full_name}</span>
            <span className="rounded-sm bg-zinc-100 px-2 py-0.5 text-xs">
              {user?.role}
            </span>
            {/* Disabled while in flight so a second click cannot fire a
                second request, and labelled so a slow cold start reads as
                "working" rather than "broken". */}
            <button
              type="button"
              onClick={logout}
              disabled={loggingOut}
              className="hover:text-zinc-900 disabled:text-zinc-400"
            >
              {loggingOut ? "Signing out…" : "Sign out"}
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-6">
        <Outlet />
      </main>
    </div>
  );
}