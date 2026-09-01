import { Route, Routes } from 'react-router-dom'

// Placeholder. The real routes land in Phase 6 -- this exists so that the
// router, the query client and Tailwind can all be verified as working
// before any of them have real screens to hide behind.
function Home() {
  return (
    <main className="mx-auto max-w-xl p-8">
      <h1 className="text-2xl font-semibold text-slate-900">
        Inventory &amp; Stock Control
      </h1>
      <p className="mt-2 text-slate-600">
        Frontend scaffold is up. If this text is spaced and styled, Tailwind is
        compiling.
      </p>
    </main>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
    </Routes>
  )
}
