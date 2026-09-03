import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./index.css";
import { ApiError } from "./api/client";

const queryClient = new QueryClient({
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
