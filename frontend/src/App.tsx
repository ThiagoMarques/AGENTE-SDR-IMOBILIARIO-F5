import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import ChatPage from "./pages/ChatPage";
import DashboardPage from "./pages/DashboardPage";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
