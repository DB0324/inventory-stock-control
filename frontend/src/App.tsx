import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth } from "./auth/guards";
import Home from "./pages/Home";
import Login from "./pages/Login";

export default function App() {
  return (
    <BrowserRouter>
      {/* AuthProvider sits inside the router because the guards it feeds use
          useLocation, and that only works below a Router. */}
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          {/* Everything nested under RequireAuth is gated. Adding a screen
              later means adding one <Route> here, not another guard. */}
          <Route element={<RequireAuth />}>
            <Route path="/" element={<Home />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
