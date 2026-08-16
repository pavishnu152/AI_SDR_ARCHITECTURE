import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { LeadsPage } from "./pages/LeadsPage";
import { LeadDetailPage } from "./pages/LeadDetailPage";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/leads"
            element={
              <ProtectedRoute>
                <LeadsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/leads/:leadId"
            element={
              <ProtectedRoute>
                <LeadDetailPage />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/leads" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
