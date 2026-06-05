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
import OrdersPage from "./pages/dashboard/OrdersPage";
import SettingsPage from "./pages/dashboard/settings/SettingsPage";
import BillingPage from "./pages/dashboard/BillingPage";
import IntegrationsPage from "./pages/dashboard/IntegrationsPage";
import ServicesPage from "./pages/dashboard/ServicesPage";
import AppointmentsPage from "./pages/dashboard/AppointmentsPage";
import ReservationsPage from "./pages/dashboard/ReservationsPage";
import AdminPage from "./pages/dashboard/AdminPage";
import NotFound from "./pages/NotFound";
import PaymentSuccessPage from "./pages/PaymentSuccessPage";
import ProtectedRoute from "@/components/ProtectedRoute";
import { AppSessionProvider, useAppSession } from "@/context/AppSessionContext";

const queryClient = new QueryClient();

function FullPageLoader() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-6">
      <div className="text-center space-y-3">
        <div className="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-muted border-t-foreground" />
        <div>
          <p className="text-sm font-medium text-foreground">Loading Duuutah AI…</p>
          <p className="text-xs text-muted-foreground">Syncing your workspace</p>
        </div>
      </div>
    </div>
  );
}

function SessionErrorScreen({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-6">
      <div className="text-center space-y-4 max-w-sm">
        <div>
          <p className="text-sm font-medium text-foreground">Unable to load your workspace</p>
          <p className="text-xs text-muted-foreground mt-1">
            We could not reach the server. This is usually temporary - please try again.
          </p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center justify-center rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
        >
          Retry
        </button>
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
  const {
    authLoaded,
    isSignedIn,
    bootstrapping,
    bootstrapError,
    activeRestaurant,
    onboardingComplete,
    refreshSession,
  } = useAppSession();

  if (!authLoaded) {
    return <FullPageLoader />;
  }

  if (isSignedIn && bootstrapping) {
    return <FullPageLoader />;
  }

  // Bootstrap failed with no restaurant loaded: do NOT assume "new user" and drop
  // them into onboarding (this is what showed working accounts the onboarding flow
  // on a transient server error). Offer a retry instead.
  if (bootstrapError && !activeRestaurant) {
    return <SessionErrorScreen onRetry={() => void refreshSession()} />;
  }

  if (activeRestaurant && onboardingComplete) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Onboarding />;
}

function ProtectedAppRoute({ children }: { children: ReactNode }) {
  const {
    authLoaded,
    isSignedIn,
    bootstrapping,
    bootstrapError,
    activeRestaurant,
    onboardingComplete,
    refreshSession,
  } = useAppSession();

  if (!authLoaded) {
    return <FullPageLoader />;
  }

  if (isSignedIn && bootstrapping) {
    return <FullPageLoader />;
  }

  // Bootstrap failed with no restaurant loaded: show a retry screen instead of
  // bouncing a (possibly fully-onboarded) account to /onboarding.
  if (bootstrapError && !activeRestaurant) {
    return <SessionErrorScreen onRetry={() => void refreshSession()} />;
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
      <Route path="orders" element={<OrdersPage />} />
      <Route path="settings" element={<SettingsPage />} />
      <Route path="billing" element={<BillingPage />} />
      <Route path="integrations" element={<IntegrationsPage />} />
      <Route path="services" element={<ServicesPage />} />
      <Route path="appointments" element={<AppointmentsPage />} />
      <Route path="reservations" element={<ReservationsPage />} />
      <Route path="admin" element={<AdminPage />} />
    </Route>
    <Route path="/payment-success" element={<PaymentSuccessPage />} />
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
