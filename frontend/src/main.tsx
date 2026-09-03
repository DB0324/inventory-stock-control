import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./index.css";
import { ApiError } from "./api/client";

/** A 401 from anywhere means the session is gone -- expired, or signed out
 *  in another tab. Send the person to log in rather than leaving them on a
 *  page where every request fails with a red banner.
 *
 *  window.location rather than the router: this can fire from outside the
 *  component tree, and a hard reload has the useful side effect of dropping
 *  every scrap of in-memory state belonging to the old session.
 */
function redirectIfSignedOut(error: unknown) {
  if (!(error instanceof ApiError && error.isUnauthenticated)) return;
  // Guard against a redirect loop: the login page's own requests 401 by
  // design before anyone has signed in.
  if (window.location.pathname === "/login") return;
  window.location.href = "/login";
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError: redirectIfSignedOut }),
  // Mutations too. Recording a movement against an expired session should
  // send you to log in, not print "Authentication credentials were not
  // provided" inside the movement form.
  mutationCache: new MutationCache({ onError: redirectIfSignedOut }),
  defaultOptions: {
    queries: {
      // Stock levels change under you when someone else records a movement,
      // so a long cache would show a confidently wrong on-hand number.
      staleTime: 10_000,
      refetchOnWindowFocus: true,
      // A 401 or 403 will not fix itself by asking again. Retry once for
      // everything else, which might genuinely be transient -- Render's free
      // tier cold start being the obvious case.
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
          return false;
        }
        return failureCount < 1;
      },
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
