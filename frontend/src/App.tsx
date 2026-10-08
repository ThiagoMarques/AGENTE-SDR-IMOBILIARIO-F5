import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import ChatPage from "./pages/ChatPage";
import DashboardPage from "./pages/DashboardPage";
import LeadPage from "./pages/LeadPage";
import TreinadorPage from "./pages/TreinadorPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/atendimento" element={<LeadPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/treinador" element={<TreinadorPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
