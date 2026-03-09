import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import LandingPage from "@/pages/LandingPage";
import Dashboard from "@/pages/Dashboard";
import CallHistory from "@/pages/CallHistory";
import MenuManager from "@/pages/MenuManager";
import Settings from "@/pages/Settings";
import LiveMonitor from "@/pages/LiveMonitor";
import Onboarding from "@/pages/Onboarding";
import SignInPage from "@/pages/SignInPage";
import SignUpPage from "@/pages/SignUpPage";
import ProtectedRoute from "@/components/ProtectedRoute";
import { AppSessionProvider, useAppSession } from "@/context/AppSessionContext";

function OnboardingGate() {
  const { activeRestaurant, onboardingComplete } = useAppSession();

  if (activeRestaurant && onboardingComplete) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Onboarding />;
}

function ProtectedAppRoute({ children }) {
  const { activeRestaurant, onboardingComplete } = useAppSession();

  if (!activeRestaurant || !onboardingComplete) {
    return <Navigate to="/onboarding" replace />;
  }

  return children;
}

function AppRoutes() {
  return (
    <>
      <Toaster position="top-right" richColors />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/sign-in/*" element={<SignInPage />} />
        <Route path="/sign-up/*" element={<SignUpPage />} />
        <Route path="/onboarding" element={<ProtectedRoute><OnboardingGate /></ProtectedRoute>} />
        <Route path="/dashboard" element={<ProtectedRoute><ProtectedAppRoute><Dashboard /></ProtectedAppRoute></ProtectedRoute>} />
        <Route path="/calls" element={<ProtectedRoute><ProtectedAppRoute><CallHistory /></ProtectedAppRoute></ProtectedRoute>} />
        <Route path="/menu" element={<ProtectedRoute><ProtectedAppRoute><MenuManager /></ProtectedAppRoute></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute><ProtectedAppRoute><Settings /></ProtectedAppRoute></ProtectedRoute>} />
        <Route path="/live" element={<ProtectedRoute><ProtectedAppRoute><LiveMonitor /></ProtectedAppRoute></ProtectedRoute>} />
      </Routes>
    </>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppSessionProvider>
        <AppRoutes />
      </AppSessionProvider>
    </BrowserRouter>
  );
}

export default App;
