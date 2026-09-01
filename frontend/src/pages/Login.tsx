import { useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";

/** What RequireAuth stashes in location.state before redirecting here. */
interface RedirectState {
  from?: { pathname: string };
}

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setPending(true);
    try {
      await login(email, password);
      const from = (location.state as RedirectState | null)?.from?.pathname ?? "/";
      navigate(from, { replace: true });
    } catch (err) {
      // An ApiError carries the server's own message ("Incorrect email or
      // password."). Anything else means the request never arrived, which is
      // a different problem and deserves a different sentence -- telling
      // someone their password is wrong when the server is down wastes their
      // time on the one thing that is not broken.
      setError(
        err instanceof ApiError ? err.message : "Could not reach the server.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-50 px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm space-y-4 rounded-md border border-zinc-200 bg-white p-6 shadow-sm"
      >
        <div>
          <h1 className="text-xl font-semibold">Inventory</h1>
          <p className="text-sm text-zinc-500">Sign in to continue</p>
        </div>

        {error && (
          // role="alert" so screen readers announce it. A failure that is
          // only visible is not a failure everyone can perceive.
          <div
            role="alert"
            className="rounded-sm bg-danger-50 px-3 py-2 text-sm text-danger-700"
          >
            {error}
          </div>
        )}

        <div className="space-y-1">
          <label htmlFor="email" className="text-xs font-medium text-zinc-600">
            Email
          </label>
          <input
            id="email"
            type="email"
            required
            // autoComplete lets password managers fill both fields. Omitting
            // it is a small thing that makes the app annoying to use daily.
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-sm border border-zinc-300 px-3 py-2 text-sm focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
          />
        </div>

        <div className="space-y-1">
          <label
            htmlFor="password"
            className="text-xs font-medium text-zinc-600"
          >
            Password
          </label>
          <input
            id="password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-sm border border-zinc-300 px-3 py-2 text-sm focus:border-accent-500 focus:ring-2 focus:ring-accent-500/40 focus:outline-none"
          />
        </div>

        <button
          type="submit"
          // Disabled while in flight, so an impatient double-click cannot
          // send two login requests.
          disabled={pending}
          className="w-full rounded-md bg-accent-600 px-3 py-2 text-sm font-medium text-white hover:bg-accent-700 disabled:bg-zinc-300"
        >
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
