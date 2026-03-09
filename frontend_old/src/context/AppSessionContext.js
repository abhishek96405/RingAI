import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useAuth, useUser } from "@clerk/clerk-react";
import { bootstrapSession, getRestaurantId, setAuthTokenGetter, setRestaurantId } from "@/lib/api";

const AppSessionContext = createContext(null);

export function AppSessionProvider({ children }) {
  const { isLoaded: authLoaded, isSignedIn, getToken } = useAuth();
  const { user } = useUser();
  const [bootstrapping, setBootstrapping] = useState(true);
  const [bootstrapData, setBootstrapData] = useState(null);

  useEffect(() => {
    setAuthTokenGetter(async () => {
      if (!isSignedIn) return null;
      return getToken();
    });
  }, [getToken, isSignedIn]);

  const refreshSession = useCallback(async (preferredRestaurantId = null) => {
    if (!isSignedIn) {
      setBootstrapData(null);
      setBootstrapping(false);
      return null;
    }

    setBootstrapping(true);
    try {
      const selectedRestaurantId = preferredRestaurantId || getRestaurantId();
      const response = await bootstrapSession(selectedRestaurantId);
      const payload = response.data;
      if (payload?.active_restaurant?.id) {
        setRestaurantId(payload.active_restaurant.id);
      }
      setBootstrapData(payload);
      return payload;
    } finally {
      setBootstrapping(false);
    }
  }, [isSignedIn]);

  useEffect(() => {
    if (!authLoaded) return;
    refreshSession();
  }, [authLoaded, refreshSession]);

  const setActiveRestaurant = useCallback(async (restaurant) => {
    if (!restaurant?.id) return;
    setRestaurantId(restaurant.id);
    setBootstrapData((current) => current ? { ...current, active_restaurant: restaurant } : current);
  }, []);

  const value = useMemo(() => ({
    authLoaded,
    isSignedIn,
    user,
    bootstrapping,
    bootstrapData,
    activeRestaurant: bootstrapData?.active_restaurant || null,
    memberships: bootstrapData?.memberships || [],
    restaurants: bootstrapData?.restaurants || [],
    onboardingComplete: bootstrapData?.onboarding_complete || false,
    refreshSession,
    setActiveRestaurant,
  }), [authLoaded, isSignedIn, user, bootstrapping, bootstrapData, refreshSession, setActiveRestaurant]);

  return <AppSessionContext.Provider value={value}>{children}</AppSessionContext.Provider>;
}

export function useAppSession() {
  const context = useContext(AppSessionContext);
  if (!context) throw new Error("useAppSession must be used inside AppSessionProvider");
  return context;
}
