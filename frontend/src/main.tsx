import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./index.css";

// Created out here, not inside a component, so a re-render can never quietly
// throw the cache away.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Stock levels change under you when someone else records a movement,
      // so a long cache would show a confidently wrong on-hand number.
      staleTime: 10_000,
      // A 401 or 403 will not fix itself by asking again. One retry, for the
      // errors that might genuinely be transient.
      retry: 1,
      refetchOnWindowFocus: true,
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
