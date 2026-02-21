import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import LandingPage from "@/pages/LandingPage";
import Dashboard from "@/pages/Dashboard";
import CallHistory from "@/pages/CallHistory";
import MenuManager from "@/pages/MenuManager";
import Settings from "@/pages/Settings";
import LiveMonitor from "@/pages/LiveMonitor";
import Onboarding from "@/pages/Onboarding";

function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" richColors />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/calls" element={<CallHistory />} />
        <Route path="/menu" element={<MenuManager />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/live" element={<LiveMonitor />} />
        <Route path="/onboarding" element={<Onboarding />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
