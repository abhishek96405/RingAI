import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { SignedIn, SignedOut, RedirectToSignIn } from "@clerk/clerk-react";
import { Toaster } from "@/components/ui/sonner";
import LandingPage from "@/pages/LandingPage";
import Dashboard from "@/pages/Dashboard";
import CallHistory from "@/pages/CallHistory";
import MenuManager from "@/pages/MenuManager";
import Settings from "@/pages/Settings";
import LiveMonitor from "@/pages/LiveMonitor";
import Onboarding from "@/pages/Onboarding";

// Protected route wrapper
const ProtectedRoute = ({ children }) => (
  <>
    <SignedIn>{children}</SignedIn>
    <SignedOut><RedirectToSignIn /></SignedOut>
  </>
);

function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" richColors />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
        <Route path="/calls" element={<ProtectedRoute><CallHistory /></ProtectedRoute>} />
        <Route path="/menu" element={<ProtectedRoute><MenuManager /></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
        <Route path="/live" element={<ProtectedRoute><LiveMonitor /></ProtectedRoute>} />
        <Route path="/onboarding" element={<ProtectedRoute><Onboarding /></ProtectedRoute>} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
