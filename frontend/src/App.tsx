import type { ReactNode } from "react";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Index from "./pages/Index";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import Onboarding from "./pages/Onboarding";
import DashboardLayout from "./components/layout/DashboardLayout";
import DashboardHome from "./pages/dashboard/DashboardHome";
import CallsPage from "./pages/dashboard/CallsPage";
import MenuPage from "./pages/dashboard/MenuPage";
import SettingsPage from "./pages/dashboard/SettingsPage";
import BillingPage from "./pages/dashboard/BillingPage";
import IntegrationsPage from "./pages/dashboard/IntegrationsPage";
import NotFound from "./pages/NotFound";
import ProtectedRoute from "@/components/ProtectedRoute";
import { AppSessionProvider, useAppSession } from "@/context/AppSessionContext";

const queryClient = new QueryClient();

function FullPageLoader() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-6">
      <div className="text-center space-y-3">
        <div className="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-foreground" />
        <div>
          <p className="text-sm font-medium text-foreground">Loading RingAI…</p>
          <p className="text-xs text-muted-foreground">Syncing your workspace</p>
        </div>
      </div>
    </div>
  );
}

function SessionReadyGate({ children }: { children: ReactNode }) {
  const { authLoaded, isSignedIn, bootstrapping } = useAppSession();

  if (!authLoaded) {
    return <FullPageLoader />;
  }

  if (isSignedIn && bootstrapping) {
    return <FullPageLoader />;
  }

  return <>{children}</>;
}

function getSignedInDestination({
  activeRestaurant,
  onboardingComplete,
}: {
  activeRestaurant: any | null;
  onboardingComplete: boolean;
}) {
  if (activeRestaurant && onboardingComplete) {
    return "/dashboard";
  }

  return "/onboarding";
}

function PublicAuthRoute({ children }: { children: ReactNode }) {
  const { authLoaded, isSignedIn, bootstrapping, activeRestaurant, onboardingComplete } =
    useAppSession();

  if (!authLoaded) {
    return <FullPageLoader />;
  }

  if (isSignedIn && bootstrapping) {
    return <FullPageLoader />;
  }

  if (isSignedIn) {
    return (
      <Navigate
        to={getSignedInDestination({ activeRestaurant, onboardingComplete })}
        replace
      />
    );
  }

  return <>{children}</>;
}

function OnboardingGate() {
  const { authLoaded, isSignedIn, bootstrapping, activeRestaurant, onboardingComplete } =
    useAppSession();

  if (!authLoaded) {
    return <FullPageLoader />;
  }

  if (isSignedIn && bootstrapping) {
    return <FullPageLoader />;
  }

  if (activeRestaurant && onboardingComplete) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Onboarding />;
}

function ProtectedAppRoute({ children }: { children: ReactNode }) {
  const { authLoaded, isSignedIn, bootstrapping, activeRestaurant, onboardingComplete } =
    useAppSession();

  if (!authLoaded) {
    return <FullPageLoader />;
  }

  if (isSignedIn && bootstrapping) {
    return <FullPageLoader />;
  }

  if (!activeRestaurant || !onboardingComplete) {
    return <Navigate to="/onboarding" replace />;
  }

  return <>{children}</>;
}

const AppRoutes = () => (
  <Routes>
    <Route path="/" element={<Index />} />
    <Route
      path="/login/*"
      element={
        <PublicAuthRoute>
          <Login />
        </PublicAuthRoute>
      }
    />
    <Route
      path="/signup/*"
      element={
        <PublicAuthRoute>
          <Signup />
        </PublicAuthRoute>
      }
    />
    <Route
      path="/onboarding"
      element={
        <ProtectedRoute>
          <SessionReadyGate>
            <OnboardingGate />
          </SessionReadyGate>
        </ProtectedRoute>
      }
    />
    <Route
      path="/dashboard"
      element={
        <ProtectedRoute>
          <SessionReadyGate>
            <ProtectedAppRoute>
              <DashboardLayout />
            </ProtectedAppRoute>
          </SessionReadyGate>
        </ProtectedRoute>
      }
    >
      <Route index element={<DashboardHome />} />
      <Route path="calls" element={<CallsPage />} />
      <Route path="menu" element={<MenuPage />} />
      <Route path="settings" element={<SettingsPage />} />
      <Route path="billing" element={<BillingPage />} />
      <Route path="integrations" element={<IntegrationsPage />} />
    </Route>
    <Route path="*" element={<NotFound />} />
  </Routes>
);

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <AppSessionProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AppSessionProvider>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;