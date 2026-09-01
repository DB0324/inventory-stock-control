import { createContext } from "react";

import type { Me } from "../types/api";

export interface AuthState {
  user: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

/** The context lives in its own module, apart from both the provider and the
 *  hook. react-refresh can only hot-reload a file that exports components and
 *  nothing else, so mixing the context in with AuthProvider would silently
 *  cost us fast refresh across the whole auth tree. ESLint enforces this. */
export const AuthContext = createContext<AuthState | null>(null);
