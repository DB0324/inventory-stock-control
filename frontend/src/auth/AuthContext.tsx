import { useEffect, useState, type ReactNode } from "react";

import { ApiError, api } from "../api/client";
import { AuthContext } from "./context";
import type { Me } from "../types/api";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Two things on mount, in this order: fetch the CSRF cookie so the very
    // first POST has a token to send, then ask who we are. A 401 here is the
    // expected answer for a fresh visitor, not an error worth logging.
    (async () => {
      try {
        await api.get("/api/auth/csrf/");
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
    setUser(await api.post<Me>("/api/auth/login/", { email, password }));
  }

  async function logout() {
    await api.post("/api/auth/logout/");
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
