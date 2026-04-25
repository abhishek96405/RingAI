import axios from "axios";

const normalizeUrl = (value?: string) => (value || "http://localhost:8001").trim().replace(/\/+$/, "");

const BACKEND_URL = normalizeUrl(import.meta.env.VITE_BACKEND_URL);
const API = `${BACKEND_URL}/api`;
const ACTIVE_RESTAURANT_KEY = "ringai.activeRestaurantId";

let authTokenGetter: null | (() => Promise<string | null | undefined>) = null;

export const setAuthTokenGetter = (getter: (() => Promise<string | null | undefined>) | null) => {
  authTokenGetter = getter;
};

export const api = axios.create({
  baseURL: API,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

api.interceptors.request.use(async (config) => {
  if (authTokenGetter) {
    const token = await authTokenGetter();
    if (token) {
      config.headers = (config.headers || {}) as import('axios').AxiosRequestHeaders;
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

const sanitizeRestaurantId = (restaurantId?: string | null) => {
  const value = typeof restaurantId === "string" ? restaurantId.trim() : "";
  if (!value || value === "null" || value === "undefined") return null;
  return value;
};

export const getRestaurantId = () => sanitizeRestaurantId(localStorage.getItem(ACTIVE_RESTAURANT_KEY));

export const setRestaurantId = (restaurantId?: string | null) => {
  const value = sanitizeRestaurantId(restaurantId);
  if (value) {
    localStorage.setItem(ACTIVE_RESTAURANT_KEY, value);
  } else {
    localStorage.removeItem(ACTIVE_RESTAURANT_KEY);
  }
};

export const clearRestaurantId = () => localStorage.removeItem(ACTIVE_RESTAURANT_KEY);

const resolveRestaurantId = (restaurantId?: string | null) => sanitizeRestaurantId(restaurantId) || getRestaurantId();

const requireRestaurantId = (restaurantId?: string | null) => {
  const resolved = resolveRestaurantId(restaurantId);
  if (!resolved) {
    throw new Error("No active restaurant selected");
  }
  return resolved;
};

const syncRestaurantFromBootstrap = (payload: any) => {
  const activeRestaurantId = sanitizeRestaurantId(payload?.active_restaurant?.id);

  if (activeRestaurantId) {
    setRestaurantId(activeRestaurantId);
    return;
  }

  const restaurants = Array.isArray(payload?.restaurants) ? payload.restaurants : [];
  if (restaurants.length === 0) {
    clearRestaurantId();
  }
};

export const bootstrapSession = async (restaurantId?: string | null) => {
  const preferredRestaurantId = resolveRestaurantId(restaurantId);

  const response = await api.get(`/me/bootstrap`, {
    params: preferredRestaurantId ? { restaurant_id: preferredRestaurantId } : {},
  });

  syncRestaurantFromBootstrap(response.data);
  return response;
};

export const selectRestaurant = async (restaurantId: string) => {
  const resolvedRestaurantId = requireRestaurantId(restaurantId);
  const response = await api.post(`/me/select-restaurant`, { restaurant_id: resolvedRestaurantId });
  setRestaurantId(resolvedRestaurantId);
  return response;
};

export const getRestaurant = (id?: string | null) => api.get(`/restaurants/${requireRestaurantId(id)}`);

export const createRestaurant = async (data: unknown) => {
  const response = await api.post(`/restaurants`, data);
  const createdRestaurantId = sanitizeRestaurantId(response.data?.id);
  if (createdRestaurantId) {
    setRestaurantId(createdRestaurantId);
  }
  return response;
};

export const updateRestaurant = (id: string | null | undefined, data: unknown) =>
  api.put(`/restaurants/${requireRestaurantId(id)}`, data);

export const getConfig = (id?: string | null) => api.get(`/restaurants/${requireRestaurantId(id)}/config`);

export const updateConfig = (id: string | null | undefined, data: unknown) =>
  api.put(`/restaurants/${requireRestaurantId(id)}/config`, data);

export const getMenuItems = (id?: string | null, category?: string) => {
  const params = category ? { category } : {};
  return api.get(`/restaurants/${requireRestaurantId(id)}/menu`, { params });
};

export const createMenuItem = (id: string | null | undefined, data: unknown) =>
  api.post(`/restaurants/${requireRestaurantId(id)}/menu`, data);

export const updateMenuItem = (itemId: string, data: unknown) => api.put(`/menu/${itemId}`, data);
export const deleteMenuItem = (itemId: string) => api.delete(`/menu/${itemId}`);
export const toggleMenuItem = (itemId: string) => api.patch(`/menu/${itemId}/toggle`);

export const getCalls = (id?: string | null, params?: Record<string, unknown>) =>
  api.get(`/restaurants/${requireRestaurantId(id)}/calls`, { params });

export const getCall = (callId: string) => api.get(`/calls/${callId}`);
export const reanalyseCall = (callId: string) => api.post(`/calls/${callId}/analyse`);

export const getAnalyticsSummary = (id?: string | null) =>
  api.get(`/restaurants/${requireRestaurantId(id)}/analytics/summary`);

export const syncMenuFromPOS = (id?: string | null) =>
  api.post(`/restaurants/${requireRestaurantId(id)}/pos/sync`);

export const savePOSCredentials = (data: any, id?: string | null) =>
  api.post(`/restaurants/${requireRestaurantId(id)}/pos/credentials`, data);

export const exportAnalytics = (startDate: string, endDate: string, id?: string | null) =>
  api.get(`/restaurants/${requireRestaurantId(id)}/analytics/export?start_date=${startDate}&end_date=${endDate}`, { responseType: "blob" });

export const getStatus = () => api.get(`/status`);
export const getTestModeStatus = () => api.get(`/test-mode/status`);
export const getTestScenarios = () => api.get(`/test-mode/scenarios`);

export const runTestScenario = (id: string | null | undefined, scenarioId: number) =>
  api.post(`/test-mode/run-scenario`, null, {
    params: { restaurant_id: requireRestaurantId(id), scenario_id: scenarioId },
  });

export const simulateCall = (id?: string | null) =>
  api.post(`/demo/simulate-call`, null, { params: { restaurant_id: requireRestaurantId(id) } });

export const seedData = (id?: string | null) =>
  api.post(`/demo/seed`, null, { params: { restaurant_id: requireRestaurantId(id) } });

export const parseMenu = (data: unknown) => api.post(`/onboarding/menu/parse`, data);

export const confirmMenu = (restaurantId: string | null | undefined, items: unknown) =>
  api.post(`/onboarding/menu/confirm`, items, {
    params: { restaurant_id: requireRestaurantId(restaurantId) },
  });

export const activateRestaurant = async (id?: string | null) => {
  const resolvedRestaurantId = requireRestaurantId(id);
  const response = await api.post(`/onboarding/activate`, { restaurant_id: resolvedRestaurantId });
  setRestaurantId(resolvedRestaurantId);
  return response;
};

export const createBillingCheckout = (payload: unknown) => api.post(`/billing/create-checkout-session`, payload);

export const getSquareConnectUrl = (restaurantId?: string | null) =>
  api.get(`/integrations/square/connect`, {
    params: { restaurant_id: requireRestaurantId(restaurantId) },
  });

export const getTwilioStatus = (restaurantId?: string | null) =>
  api.get(`/integrations/twilio/status`, {
    params: { restaurant_id: requireRestaurantId(restaurantId) },
  });

export const provisionTwilioNumber = (restaurantId?: string | null, areaCode?: string) =>
  api.post(`/integrations/twilio/provision-number`, {
    restaurant_id: requireRestaurantId(restaurantId),
    area_code: areaCode || undefined,
  });

export const assignTwilioNumber = (restaurantId: string | null | undefined, phoneNumber: string) =>
  api.post(`/integrations/twilio/assign-existing-number`, {
    restaurant_id: requireRestaurantId(restaurantId),
    phone_number: phoneNumber,
  });

export const getServices = (restaurantId?: string | null) =>
  api.get(`/restaurants/${requireRestaurantId(restaurantId)}/services`);

export const createService = (restaurantId: string | null | undefined, data: unknown) =>
  api.post(`/restaurants/${requireRestaurantId(restaurantId)}/services`, data);

export const updateService = (serviceId: string, data: unknown) =>
  api.put(`/services/${serviceId}`, data);

export const deleteService = (serviceId: string) =>
  api.delete(`/services/${serviceId}`);

export const getAppointments = (restaurantId?: string | null, params?: Record<string, unknown>) =>
  api.get(`/restaurants/${requireRestaurantId(restaurantId)}/appointments`, { params });

export const getAppointment = (appointmentId: string) =>
  api.get(`/appointments/${appointmentId}`);

export const cancelAppointment = (appointmentId: string) =>
  api.patch(`/appointments/${appointmentId}/cancel`);

export const bookAppointment = (restaurantId: string | null | undefined, data: unknown) =>
  api.post(`/restaurants/${requireRestaurantId(restaurantId)}/calendar/book`, data);

export const getBlockedSlots = (restaurantId: string, date: string) =>
  api.get(`/restaurants/${restaurantId}/blocked-slots`, { params: { date } });

export const blockSlot = (
  restaurantId: string,
  data: { date: string; slot_time: string; reason?: string }
) => api.post(`/restaurants/${restaurantId}/blocked-slots`, data);

export const unblockSlot = (restaurantId: string, slotId: string) =>
  api.delete(`/restaurants/${restaurantId}/blocked-slots/${slotId}`);

// Modifier Groups
export const getModifierGroups = (restaurantId: string) =>
  api.get(`/restaurants/${restaurantId}/modifier-groups`);

export const createModifierGroup = (restaurantId: string, data: any) =>
  api.post(`/restaurants/${restaurantId}/modifier-groups`, data);

export const updateModifierGroup = (groupId: string, data: any) =>
  api.put(`/modifier-groups/${groupId}`, data);

export const deleteModifierGroup = (groupId: string) =>
  api.delete(`/modifier-groups/${groupId}`);

export const updateItemModifierAssignments = (itemId: string, assignments: any[]) =>
  api.put(`/menu/${itemId}/modifier-assignments`, assignments);

export const getVoicePreview = (voiceName: string) =>
  api.get(`/voice-preview/${voiceName}`);

export const getAdminCostAnalytics = (days: number = 30) =>
  api.get(`/admin/cost-analytics?days=${days}`);

export const getAvailableSlots = (restaurantId: string, date: string, serviceName?: string) =>
  api.get(`/restaurants/${restaurantId}/available-slots`, {
    params: { date, service_name: serviceName },
  });

export const getCalendarStatus = (restaurantId?: string | null) =>
  api.get(`/restaurants/${requireRestaurantId(restaurantId)}/calendar/status`);

export const connectGoogleCalendar = (restaurantId?: string | null) =>
  api.get(`/calendar/google/connect`, {
    params: { restaurant_id: requireRestaurantId(restaurantId) },
  });

export const disconnectGoogleCalendar = (restaurantId?: string | null) =>
  api.delete(`/restaurants/${requireRestaurantId(restaurantId)}/calendar/disconnect`);

export const getCalendarAvailability = (restaurantId: string | null | undefined, date: string, serviceId?: string) =>
  api.get(`/restaurants/${requireRestaurantId(restaurantId)}/calendar/availability`, {
    params: { date, service_id: serviceId },
  });

// ── Reservations ──
export const getReservations = (restaurantId?: string | null, params?: Record<string, unknown>) =>
  api.get(`/restaurants/${requireRestaurantId(restaurantId)}/reservations`, { params });

export const updateReservation = (restaurantId: string | null | undefined, reservationId: string, data: unknown) =>
  api.patch(`/restaurants/${requireRestaurantId(restaurantId)}/reservations/${reservationId}`, data);

export const deleteReservation = (restaurantId: string | null | undefined, reservationId: string) =>
  api.delete(`/restaurants/${requireRestaurantId(restaurantId)}/reservations/${reservationId}`);

export const getReservationSlots = (restaurantId: string | null | undefined, date: string) =>
  api.get(`/restaurants/${requireRestaurantId(restaurantId)}/reservations/slots`, { params: { date } });

// ── POS Test Connection ──
export const testPOSConnection = (id?: string | null) =>
  api.post(`/restaurants/${requireRestaurantId(id)}/pos/test`);

// ── AI Learning ──
export const getLearningStats = (restaurantId?: string | null) =>
  api.get(`/restaurants/${requireRestaurantId(restaurantId)}/learning/stats`);

export const getLearningAliases = (restaurantId?: string | null) =>
  api.get(`/restaurants/${requireRestaurantId(restaurantId)}/learning/aliases`);

export const approveLearningAlias = (restaurantId: string | null | undefined, aliasId: string) =>
  api.post(`/restaurants/${requireRestaurantId(restaurantId)}/learning/aliases/${aliasId}/approve`);

export const rejectLearningAlias = (restaurantId: string | null | undefined, aliasId: string) =>
  api.post(`/restaurants/${requireRestaurantId(restaurantId)}/learning/aliases/${aliasId}/reject`);

export const getFlaggedCalls = (restaurantId?: string | null) =>
  api.get(`/restaurants/${requireRestaurantId(restaurantId)}/learning/flagged-calls`);

export default api;