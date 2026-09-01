import { useContext } from "react";

import { AuthContext } from "./context";

/** Split out of AuthContext.tsx so that file exports components only.
 *  eslint-plugin-react-refresh warns when a module mixes a component with a
 *  plain export, because it breaks hot reloading for the whole module. */
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
