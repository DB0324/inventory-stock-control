import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth } from "./auth/guards";
import Layout from "./components/Layout";
import ItemDetail from "./pages/ItemDetail";
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
              <Route path="/" element={<ItemList />} />
              <Route path="/items/:id" element={<ItemDetail />} />
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
