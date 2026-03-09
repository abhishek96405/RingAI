import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useAuth, useUser } from "@clerk/clerk-react";
import {
  bootstrapSession,
  clearRestaurantId,
  getRestaurantId,
  selectRestaurant,
  setAuthTokenGetter,
  setRestaurantId,
} from "@/lib/api";

type BootstrapPayload = {
  active_restaurant?: any;
  memberships?: any[];
  restaurants?: any[];
  onboarding_complete?: boolean;
  user?: any;
};

type SessionContextType = {
  authLoaded: boolean;
  isSignedIn: boolean | undefined;
  user: any;
  bootstrapping: boolean;
  bootstrapData: BootstrapPayload | null;
  activeRestaurant: any | null;
  memberships: any[];
  restaurants: any[];
  onboardingComplete: boolean;
  refreshSession: (preferredRestaurantId?: string | null) => Promise<BootstrapPayload | null>;
  setActiveRestaurant: (restaurant: any) => Promise<void>;
};

const AppSessionContext = createContext<SessionContextType | null>(null);

const getSafeRestaurants = (payload: BootstrapPayload | null | undefined) =>
  Array.isArray(payload?.restaurants) ? payload!.restaurants! : [];

const getSafeMemberships = (payload: BootstrapPayload | null | undefined) =>
  Array.isArray(payload?.memberships) ? payload!.memberships! : [];

const getResolvedActiveRestaurant = (payload: BootstrapPayload | null | undefined) => {
  if (payload?.active_restaurant?.id) return payload.active_restaurant;
  const restaurants = getSafeRestaurants(payload);
  return restaurants.length > 0 ? restaurants[0] : null;
};

const getResolvedOnboardingComplete = (payload: BootstrapPayload | null | undefined) => {
  const activeRestaurant = getResolvedActiveRestaurant(payload);
  if (activeRestaurant) {
    return Boolean(activeRestaurant.is_active);
  }
  return false;
};

export function AppSessionProvider({ children }: { children: ReactNode }) {
  const { isLoaded: authLoaded, isSignedIn, getToken } = useAuth();
  const { user } = useUser();

  const [bootstrapping, setBootstrapping] = useState(true);
  const [bootstrapData, setBootstrapData] = useState<BootstrapPayload | null>(null);

  useEffect(() => {
    setAuthTokenGetter(async () => {
      if (!isSignedIn) return null;
      return getToken();
    });

    return () => {
      setAuthTokenGetter(null);
    };
  }, [getToken, isSignedIn]);

  const resetSessionState = useCallback(() => {
    clearRestaurantId();
    setBootstrapData(null);
    setBootstrapping(false);
  }, []);

  const refreshSession = useCallback(
    async (preferredRestaurantId: string | null = null) => {
      if (!authLoaded) {
        return null;
      }

      if (!isSignedIn) {
        resetSessionState();
        return null;
      }

      setBootstrapping(true);

      try {
        const selectedRestaurantId = preferredRestaurantId || getRestaurantId() || null;
        const response = await bootstrapSession(selectedRestaurantId);
        const payload = (response.data || null) as BootstrapPayload | null;

        const resolvedActiveRestaurant = getResolvedActiveRestaurant(payload);

        if (resolvedActiveRestaurant?.id) {
          setRestaurantId(resolvedActiveRestaurant.id);
        } else {
          clearRestaurantId();
        }

        setBootstrapData(payload);
        return payload;
      } catch (error) {
        console.error("Failed to bootstrap session", error);
        resetSessionState();
        return null;
      } finally {
        setBootstrapping(false);
      }
    },
    [authLoaded, isSignedIn, resetSessionState]
  );

  useEffect(() => {
    if (!authLoaded) return;

    refreshSession();
  }, [authLoaded, isSignedIn, refreshSession]);

  const setActiveRestaurant = useCallback(
    async (restaurant: any) => {
      if (!restaurant?.id) return;

      setBootstrapping(true);

      try {
        await selectRestaurant(restaurant.id);
        setRestaurantId(restaurant.id);

        setBootstrapData((current) => {
          if (!current) {
            return {
              active_restaurant: restaurant,
              memberships: [],
              restaurants: [restaurant],
              onboarding_complete: Boolean(restaurant?.is_active),
            };
          }

          const existingRestaurants = Array.isArray(current.restaurants) ? current.restaurants : [];
          const nextRestaurants = existingRestaurants.some((item: any) => item?.id === restaurant.id)
            ? existingRestaurants.map((item: any) => (item?.id === restaurant.id ? restaurant : item))
            : [restaurant, ...existingRestaurants];

          return {
            ...current,
            active_restaurant: restaurant,
            restaurants: nextRestaurants,
            onboarding_complete: Boolean(restaurant?.is_active),
          };
        });
      } catch (error) {
        console.error("Failed to select restaurant", error);
        await refreshSession(restaurant.id);
      } finally {
        setBootstrapping(false);
      }
    },
    [refreshSession]
  );

  const activeRestaurant = getResolvedActiveRestaurant(bootstrapData);
  const restaurants = getSafeRestaurants(bootstrapData);
  const memberships = getSafeMemberships(bootstrapData);
  const onboardingComplete = getResolvedOnboardingComplete(bootstrapData);

  const value = useMemo<SessionContextType>(
    () => ({
      authLoaded,
      isSignedIn,
      user,
      bootstrapping,
      bootstrapData,
      activeRestaurant,
      memberships,
      restaurants,
      onboardingComplete,
      refreshSession,
      setActiveRestaurant,
    }),
    [
      authLoaded,
      isSignedIn,
      user,
      bootstrapping,
      bootstrapData,
      activeRestaurant,
      memberships,
      restaurants,
      onboardingComplete,
      refreshSession,
      setActiveRestaurant,
    ]
  );

  return <AppSessionContext.Provider value={value}>{children}</AppSessionContext.Provider>;
}

export function useAppSession() {
  const context = useContext(AppSessionContext);
  if (!context) {
    throw new Error("useAppSession must be used inside AppSessionProvider");
  }
  return context;
}