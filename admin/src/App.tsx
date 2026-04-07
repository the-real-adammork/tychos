import { Routes, Route, Navigate } from "react-router-dom";
import { useState, useEffect, createContext, useContext } from "react";
import { Sidebar } from "@/components/sidebar";

import DashboardPage from "@/pages/DashboardPage";
import LoginPage from "@/pages/LoginPage";
import RegisterPage from "@/pages/RegisterPage";
import ParametersPage from "@/pages/ParametersPage";
import ParamDetailPage from "@/pages/ParamDetailPage";
import ParamEditPage from "@/pages/ParamEditPage";
import ParamVersionDetailPage from "@/pages/ParamVersionDetailPage";
import RunsPage from "@/pages/RunsPage";
import ResultsPage from "@/pages/ResultsPage";
import ResultDetailPage from "@/pages/ResultDetailPage";
import ComparePage from "@/pages/ComparePage";
import DatasetsPage from "@/pages/DatasetsPage";
import DatasetDetailPage from "@/pages/DatasetDetailPage";
import EclipseCatalogDetailPage from "@/pages/EclipseCatalogDetailPage";

type User = { id: number; email: string; name: string } | null;

const AuthContext = createContext<{ user: User; setUser: (u: User) => void }>({
  user: null,
  setUser: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export default function App() {
  const [user, setUser] = useState<User>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/auth/me")
      .then((r) => (r.ok ? r.json() : null))
      .then((u) => setUser(u))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return null;

  return (
    <AuthContext.Provider value={{ user, setUser }}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/*"
          element={
            user ? (
              <div className="flex h-screen overflow-hidden">
                <Sidebar userName={user.name} userEmail={user.email} />
                <main className="flex-1 overflow-y-auto p-6">
                  <Routes>
                    <Route path="/" element={<DashboardPage />} />
                    <Route path="/parameters" element={<ParametersPage />} />
                    <Route path="/parameters/:id" element={<ParamDetailPage />} />
                    <Route path="/parameters/:id/edit" element={<ParamEditPage />} />
                    <Route path="/parameters/:id/versions/:versionId" element={<ParamVersionDetailPage />} />
                    <Route path="/runs" element={<RunsPage />} />
                    <Route path="/results/:runId" element={<ResultsPage />} />
                    <Route path="/results/:runId/:resultId" element={<ResultDetailPage />} />
                    <Route path="/datasets" element={<DatasetsPage />} />
                    <Route path="/datasets/:slug" element={<DatasetDetailPage />} />
                    <Route path="/datasets/:slug/:eclipseId" element={<EclipseCatalogDetailPage />} />
                    <Route path="/compare" element={<ComparePage />} />
                  </Routes>
                </main>
              </div>
            ) : (
              <Navigate to="/login" />
            )
          }
        />
      </Routes>
    </AuthContext.Provider>
  );
}
