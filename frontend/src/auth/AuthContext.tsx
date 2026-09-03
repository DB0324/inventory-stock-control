import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";

import { ApiError, api, primeCsrfToken } from "../api/client";
import { AuthContext } from "./context";
import type { Me } from "../types/api";

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  // Signing out hits the network, and on a cold Render instance that is tens
  // of seconds. Without this the button looks broken while it works.
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => {
    // Two things on mount, in this order: fetch the CSRF cookie so the very
    // first POST has a token to send, then ask who we are. A 401 here is the
    // expected answer for a fresh visitor, not an error worth logging.
    (async () => {
      try {
        await primeCsrfToken();
        setUser(await api.get<Me>("/api/auth/me/"));
      } catch (error) {
        if (!(error instanceof ApiError && error.isUnauthenticated)) {
          console.error(error);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function login(email: string, password: string) {
    // The login response is the same shape as /me/, so there is no need for
    // a follow-up request to learn the user's role and locations.
    const me = await api.post<Me>("/api/auth/login/", { email, password });
    // Django rotates the CSRF secret when a session begins, which invalidates
    // the token we signed in with. Without re-priming, the very next write --
    // signing out, recording a movement -- fails CSRF for no visible reason.
    await primeCsrfToken();
    setUser(me);
  }

  async function logout() {
    setLoggingOut(true);
    try {
      await api.post("/api/auth/logout/");
    } catch (error) {
      // Deliberately swallowed. If the server call fails -- it is asleep, the
      // network dropped, the session had already expired -- the safe direction
      // is still to sign out locally. Leaving someone logged in because the
      // logout request failed is the worse of the two errors, and the session
      // cookie is useless to them once the client forgets the user anyway.
      console.error("Logout request failed; signing out locally.", error);
    } finally {
      setUser(null);
      // Drop every cached query. Without this, the next person to sign in on
      // this browser sees the previous user's items and timelines from cache
      // before their own data arrives -- and for a staff account that is data
      // their role is not supposed to reach.
      queryClient.clear();
      setLoggingOut(false);
    }
  }

  return (
    <AuthContext.Provider value={{ user, loading, loggingOut, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
