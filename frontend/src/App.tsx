import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth, RequireManager } from "./auth/guards";
import Layout from "./components/Layout";
import Alerts from "./pages/Alerts";
import Dashboard from "./pages/Dashboard";
import ItemDetail from "./pages/ItemDetail";
import ImportExport from "./pages/ImportExport";
import ItemForm from "./pages/ItemForm";
import Locations from "./pages/Locations";
import ItemList from "./pages/ItemList";
import Login from "./pages/Login";

export default function App() {
  return (
    <BrowserRouter>
      {/* AuthProvider sits inside the router because the guards it feeds use
          useLocation, which only works below a Router. */}
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<RequireAuth />}>
            {/* Layout renders the header and an <Outlet>, so every gated page
                gets the chrome without repeating it. */}
            <Route element={<Layout />}>
              {/* The brief calls the dashboard "a landing view", so it takes
                  the root and items move to their own path. */}
              <Route path="/" element={<Dashboard />} />
              <Route path="/items" element={<ItemList />} />
              {/* Before /items/:id, or "new" would be read as an id. */}
              <Route path="/items/new" element={<ItemForm />} />
              <Route path="/items/:id/edit" element={<ItemForm />} />
              <Route path="/items/:id" element={<ItemDetail />} />
              {/* Readable by both roles; only managers see a Dismiss button,
                  and only the server can actually refuse one. */}
              <Route path="/alerts" element={<Alerts />} />
              {/* Manager-only, and the API says so too -- this guard only
                  saves staff from loading a page that would 403. */}
              <Route element={<RequireManager />}>
                <Route path="/locations" element={<Locations />} />
                <Route path="/data" element={<ImportExport />} />
              </Route>
            </Route>
          </Route>
          {/* Load-bearing. Vercel now rewrites every unknown path to
              index.html, so without this a typo in the URL renders a blank
              page instead of saying anything. */}
          <Route
            path="*"
            element={
              <div className="p-8 text-center text-sm text-zinc-500">
                Page not found.
              </div>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
