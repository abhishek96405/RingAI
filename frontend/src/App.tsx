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
import AILearningPage from "./pages/dashboard/AILearningPage";
import AdminPage from "./pages/dashboard/AdminPage";
import NotFound from "./pages/NotFound";
import PaymentSuccessPage from "./pages/PaymentSuccessPage";
import CloverCallbackPage from "./pages/CloverCallbackPage";
import SquareCallbackPage from "./pages/SquareCallbackPage";
import PrivacyPolicy from "./pages/PrivacyPolicy";
import ProtectedRoute from "@/components/ProtectedRoute";
import { AppSessionProvider, useAppSession } from "@/context/AppSessionContext";

const queryClient = new QueryClient();

function FullPageLoader() {
  return (
    <div className="dash dash-surface min-h-screen flex items-center justify-center px-6">
      <div className="text-center space-y-3">
        <div className="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-line border-t-coral" />
        <div>
          <p className="text-sm font-medium text-ink">Loading Duuutah AI…</p>
          <p className="text-xs text-ink-soft">Syncing your workspace</p>
        </div>
      </div>
    </div>
  );
}

function SessionErrorScreen({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="dash dash-surface min-h-screen flex items-center justify-center px-6">
      <div className="text-center space-y-4 max-w-sm">
        <div>
          <p className="text-sm font-medium text-ink">Unable to load your workspace</p>
          <p className="text-xs text-ink-soft mt-1">
            We could not reach the server. This is usually temporary - please try again.
          </p>
        </div>
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center justify-center rounded-md bg-coral px-5 py-2 text-sm font-medium text-white hover:bg-coral-deep"
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
      <Route path="learning" element={<AILearningPage />} />
      <Route path="admin" element={<AdminPage />} />
    </Route>
    <Route path="/payment-success" element={<PaymentSuccessPage />} />
    <Route path="/privacy" element={<PrivacyPolicy />} />
    {/* Clover OAuth callback. Top-level (NOT under /dashboard) so the path
        matches CLOVER_REDIRECT_URI exactly. Deliberately NOT wrapped in
        ProtectedAppRoute/PublicAuthRoute — the page handles its own auth states;
        a wrapper would redirect and destroy the OAuth query params. */}
    <Route path="/integrations/clover/callback" element={<CloverCallbackPage />} />
    {/* Square OAuth landing. The backend square_callback does the exchange and
        redirects the browser here; this page is display-only. Top-level and
        UNWRAPPED for the same reason as Clover's — a route guard would redirect
        and destroy the status/merchant_id/reason query params. */}
    <Route path="/integrations/square/callback" element={<SquareCallbackPage />} />
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
