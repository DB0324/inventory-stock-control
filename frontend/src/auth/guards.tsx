import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "./useAuth";

/** Shown while the mount-time /me/ request is still in flight. Without this,
 *  a logged-in user reloading the page is briefly treated as anonymous and
 *  bounced to /login before the answer arrives. */
function Loading() {
  return <div className="p-6 text-sm text-zinc-500">Loading…</div>;
}

export function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Loading />;
  // `state` carries where they were headed, so login can send them back there
  // instead of dumping everyone on the home page. `replace` keeps the
  // redirect out of history -- otherwise Back returns to the guarded route.
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />;
  return <Outlet />;
}

export function RequireManager() {
  const { user, loading } = useAuth();

  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  // Convenience only. The server returns 403 regardless -- goal 1 says the
  // rule must be enforced there, and the tests hit the endpoints directly.
  // This guard exists so staff do not see a page that would only fail.
  if (!user.is_manager) return <Navigate to="/" replace />;
  return <Outlet />;
}
