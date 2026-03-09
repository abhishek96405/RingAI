import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8001";
const API = `${BACKEND_URL}/api`;
const ACTIVE_RESTAURANT_KEY = "ringai.activeRestaurantId";

let authTokenGetter = null;

export const setAuthTokenGetter = (getter) => {
  authTokenGetter = getter;
};

export const api = axios.create({
  baseURL: API,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use(async (config) => {
  if (authTokenGetter) {
    const token = await authTokenGetter();
    if (token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

export const getRestaurantId = () => localStorage.getItem(ACTIVE_RESTAURANT_KEY);

export const setRestaurantId = (restaurantId) => {
  if (restaurantId) {
    localStorage.setItem(ACTIVE_RESTAURANT_KEY, restaurantId);
  }
};

export const clearRestaurantId = () => {
  localStorage.removeItem(ACTIVE_RESTAURANT_KEY);
};

// Session / tenant bootstrap
export const bootstrapSession = (restaurantId) =>
  api.get(`/me/bootstrap`, {
    params: restaurantId ? { restaurant_id: restaurantId } : {},
  });

export const selectRestaurant = (restaurantId) =>
  api.post(`/me/select-restaurant`, { restaurant_id: restaurantId });

// Restaurant
export const getRestaurant = (id) =>
  api.get(`/restaurants/${id || getRestaurantId()}`);

export const createRestaurant = (data) =>
  api.post(`/restaurants`, data);

export const updateRestaurant = (id, data) =>
  api.put(`/restaurants/${id || getRestaurantId()}`, data);

// Config
export const getConfig = (id) =>
  api.get(`/restaurants/${id || getRestaurantId()}/config`);

export const updateConfig = (id, data) =>
  api.put(`/restaurants/${id || getRestaurantId()}/config`, data);

// Menu
export const getMenuItems = (id, category) => {
  const params = category ? { category } : {};
  return api.get(`/restaurants/${id || getRestaurantId()}/menu`, { params });
};

export const createMenuItem = (id, data) =>
  api.post(`/restaurants/${id || getRestaurantId()}/menu`, data);

export const updateMenuItem = (itemId, data) =>
  api.put(`/menu/${itemId}`, data);

export const deleteMenuItem = (itemId) =>
  api.delete(`/menu/${itemId}`);

export const toggleMenuItem = (itemId) =>
  api.patch(`/menu/${itemId}/toggle`);

// Calls
export const getCalls = (id, params) =>
  api.get(`/restaurants/${id || getRestaurantId()}/calls`, { params });

export const getCall = (callId) =>
  api.get(`/calls/${callId}`);

export const reanalyseCall = (callId) =>
  api.post(`/calls/${callId}/analyse`);

// Analytics
export const getAnalyticsSummary = (id) =>
  api.get(`/restaurants/${id || getRestaurantId()}/analytics/summary`);

// Status & test mode
export const getStatus = () =>
  api.get(`/status`);

export const getTestModeStatus = () =>
  api.get(`/test-mode/status`);

export const getTestScenarios = () =>
  api.get(`/test-mode/scenarios`);

export const runTestScenario = (id, scenarioId) =>
  api.post(`/test-mode/run-scenario`, null, {
    params: {
      restaurant_id: id || getRestaurantId(),
      scenario_id: scenarioId,
    },
  });

// Demo / onboarding
export const simulateCall = (id) =>
  api.post(`/demo/simulate-call`, null, {
    params: { restaurant_id: id || getRestaurantId() },
  });

export const seedData = (id) =>
  api.post(`/demo/seed`, null, {
    params: { restaurant_id: id || getRestaurantId() },
  });

export const parseMenu = (data) =>
  api.post(`/onboarding/menu/parse`, data);

export const confirmMenu = (restaurantId, items) =>
  api.post(`/onboarding/menu/confirm`, items, {
    params: { restaurant_id: restaurantId || getRestaurantId() },
  });

export const activateRestaurant = (id) =>
  api.post(`/onboarding/activate`, {
    restaurant_id: id || getRestaurantId(),
  });

// Billing
export const createBillingCheckout = (payload) =>
  api.post(`/billing/create-checkout-session`, payload);

// Square
export const getSquareConnectUrl = (restaurantId) =>
  api.get(`/integrations/square/connect`, {
    params: { restaurant_id: restaurantId || getRestaurantId() },
  });

// Twilio
export const getTwilioStatus = (restaurantId) =>
  api.get(`/integrations/twilio/status`, {
    params: { restaurant_id: restaurantId || getRestaurantId() },
  });

export const provisionTwilioNumber = (restaurantId, areaCode) =>
  api.post(`/integrations/twilio/provision-number`, {
    restaurant_id: restaurantId || getRestaurantId(),
    area_code: areaCode || undefined,
  });

export const assignTwilioNumber = (restaurantId, phoneNumber) =>
  api.post(`/integrations/twilio/assign-existing-number`, {
    restaurant_id: restaurantId || getRestaurantId(),
    phone_number: phoneNumber,
  });

export default api;