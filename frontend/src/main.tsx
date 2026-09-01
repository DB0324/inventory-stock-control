import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'

// One client for the whole app. Created out here rather than inside a
// component so a re-render can never quietly throw the cache away.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The backend is the only source of truth for stock levels, and they
      // change under you when someone else records a movement. Short and
      // honest beats a long cache that shows a stale on-hand number.
      staleTime: 10_000,
      // A 401 or a 403 will not fix itself by asking again. Only retry once,
      // and only for the errors that might actually be transient.
      retry: 1,
      refetchOnWindowFocus: true,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
