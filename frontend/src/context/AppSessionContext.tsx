import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useAuth, useUser } from "@clerk/clerk-react";
import {
  bootstrapSession,
  clearRestaurantId,
  getRestaurantId,
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
  bootstrapError: boolean;
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
  Array.isArray(payload?.restaurants) ? payload.restaurants : [];

const getSafeMemberships = (payload: BootstrapPayload | null | undefined) =>
  Array.isArray(payload?.memberships) ? payload.memberships : [];

const getResolvedActiveRestaurant = (payload: BootstrapPayload | null | undefined) => {
  if (payload?.active_restaurant?.id) return payload.active_restaurant;
  const restaurants = getSafeRestaurants(payload);
  return restaurants.length > 0 ? restaurants[0] : null;
};

const getResolvedOnboardingComplete = (payload: BootstrapPayload | null | undefined) => {
  if (typeof payload?.onboarding_complete === "boolean") {
    return payload.onboarding_complete;
  }

  const activeRestaurant = getResolvedActiveRestaurant(payload);
  return Boolean(activeRestaurant?.is_active);
};

export function AppSessionProvider({ children }: { children: ReactNode }) {
  const { isLoaded: authLoaded, isSignedIn, getToken } = useAuth();
  const { user } = useUser();

  const [tokenResolved, setTokenResolved] = useState(false);
  const [bootstrapping, setBootstrapping] = useState(true);
  const [bootstrapError, setBootstrapError] = useState(false);
  const [bootstrapData, setBootstrapData] = useState<BootstrapPayload | null>(null);

  const bootstrapDataRef = useRef<BootstrapPayload | null>(null);

  useEffect(() => {
    bootstrapDataRef.current = bootstrapData;
  }, [bootstrapData]);

  useEffect(() => {
    let cancelled = false;

    const configureTokenGetter = async () => {
      if (!authLoaded) return;

      if (!isSignedIn) {
        setAuthTokenGetter(null);
        if (!cancelled) setTokenResolved(true);
        return;
      }

      const getter = async () => {
        try {
          return await getToken();
        } catch (error) {
          console.error("Failed to obtain Clerk token", error);
          return null;
        }
      };

      setAuthTokenGetter(getter);

      try {
        await getter();
      } finally {
        if (!cancelled) setTokenResolved(true);
      }
    };

    setTokenResolved(false);
    void configureTokenGetter();

    return () => {
      cancelled = true;
      setAuthTokenGetter(null);
    };
  }, [authLoaded, isSignedIn, getToken]);

  const resetSessionState = useCallback(() => {
    clearRestaurantId();
    setBootstrapData(null);
    setBootstrapError(false);
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
        setBootstrapError(false);
        return payload;
      } catch (error) {
        console.error("Failed to bootstrap session", error);
        setBootstrapError(true);
        return bootstrapDataRef.current;
      } finally {
        setBootstrapping(false);
      }
    },
    [authLoaded, isSignedIn, resetSessionState]
  );

  useEffect(() => {
    if (!authLoaded) return;
    if (!tokenResolved) return;

    if (!isSignedIn) {
      resetSessionState();
      return;
    }

    void refreshSession();
  }, [authLoaded, tokenResolved, isSignedIn, refreshSession, resetSessionState]);

  const setActiveRestaurant = useCallback(async (restaurant: any) => {
    if (!restaurant?.id) return;

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
  }, []);

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
      bootstrapError,
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
      bootstrapError,
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