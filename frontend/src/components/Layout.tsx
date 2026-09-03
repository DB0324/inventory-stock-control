import { useQuery } from "@tanstack/react-query";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";

import { inventory } from "../api/inventory";

import { useAuth } from "../auth/useAuth";

export default function Layout() {
  const { user, logout, loggingOut } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();

  // Navigate explicitly rather than trusting RequireAuth to notice that the
  // user went null. It should -- it is a context consumer and re-renders --
  // but stranding someone on a page whose every request 401s is bad enough
  // that this path is worth making unconditional.
  async function handleSignOut() {
    await logout();
    navigate("/login", { replace: true });
  }

  // The badge is on every screen, so it gets its own lightweight endpoint
  // rather than counting a page of serialized items. Refetched on an interval
  // because stock falls low because of what *other* people record, not
  // because of anything this tab did.
  const alertCount = useQuery({
    queryKey: ["alert-count"],
    queryFn: inventory.alertCount,
    refetchInterval: 60_000,
  });
  const lowStock = alertCount.data?.count ?? 0;

  const links = [
    { to: "/", label: "Dashboard", badge: 0 },
    { to: "/items", label: "Items", badge: 0 },
    { to: "/alerts", label: "Low stock", badge: lowStock },
    // Manager-only link for a manager-only page. Absent rather than disabled:
    // staff have nothing to do there, and the server refuses either way.
    ...(user?.is_manager
      ? [
          { to: "/locations", label: "Locations", badge: 0 },
          { to: "/data", label: "Import / export", badge: 0 },
        ]
      : []),
  ];

  return (
    <div className="min-h-screen bg-zinc-50">
      {/* Sticky rather than fixed: sticky keeps the header in normal flow, so
          the main content below still starts underneath it. A fixed header
          would be lifted out of flow and the first rows of every page would
          slide up behind it, needing a matching top padding to compensate.
          bg-white has to stay opaque for the same reason -- content scrolls
          under this, not past it. */}
      <header className="sticky top-0 z-20 border-b border-zinc-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3">
          <span className="font-semibold">Inventory</span>
          <nav className="flex gap-4 text-sm">
            {links.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={`flex items-center gap-1.5 ${
                  pathname === link.to
                    ? "font-medium text-accent-700"
                    : "text-zinc-600 hover:text-zinc-900"
                }`}
              >
                {link.label}
                {link.badge > 0 && (
                  // Amber, not red. These are things to order, not failures --
                  // red is reserved for something having gone wrong.
                  <span
                    className="rounded-full bg-amber-100 px-1.5 py-0.5 text-xs font-medium tabular-nums text-amber-800"
                    aria-label={`${link.badge} items low on stock`}
                  >
                    {link.badge}
                  </span>
                )}
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
              onClick={handleSignOut}
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