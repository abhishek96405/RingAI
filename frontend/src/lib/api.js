import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Restaurant ID management - uses localStorage to persist user's restaurant
const STORAGE_KEY = "ringai_restaurant_id";

export const setRestaurantId = (id) => {
  localStorage.setItem(STORAGE_KEY, id);
};

export const getRestaurantId = () => {
  return localStorage.getItem(STORAGE_KEY) || null;
};

export const clearRestaurantId = () => {
  localStorage.removeItem(STORAGE_KEY);
};

export const api = axios.create({
  baseURL: API,
  headers: { "Content-Type": "application/json" },
});

// Helper to get restaurant ID or throw error
const requireRestaurantId = () => {
  const id = getRestaurantId();
  if (!id) throw new Error("No restaurant configured. Please complete onboarding.");
  return id;
};

// Restaurant
export const getRestaurant = (id) => api.get(`/restaurants/${id || requireRestaurantId()}`);
export const updateRestaurant = (id, data) => api.put(`/restaurants/${id || requireRestaurantId()}`, data);
export const getRestaurants = () => api.get(`/restaurants`);

// Config
export const getConfig = (id) => api.get(`/restaurants/${id || requireRestaurantId()}/config`);
export const updateConfig = (id, data) => api.put(`/restaurants/${id || requireRestaurantId()}/config`, data);

// Menu
export const getMenuItems = (id, category) => {
  const params = category ? { category } : {};
  return api.get(`/restaurants/${id || requireRestaurantId()}/menu`, { params });
};
export const createMenuItem = (id, data) => api.post(`/restaurants/${id || requireRestaurantId()}/menu`, data);
export const updateMenuItem = (itemId, data) => api.put(`/menu/${itemId}`, data);
export const deleteMenuItem = (itemId) => api.delete(`/menu/${itemId}`);
export const toggleMenuItem = (itemId) => api.patch(`/menu/${itemId}/toggle`);

// Calls
export const getCalls = (id, params) => api.get(`/restaurants/${id || requireRestaurantId()}/calls`, { params });
export const getCall = (callId) => api.get(`/calls/${callId}`);
export const reanalyseCall = (callId) => api.post(`/calls/${callId}/analyse`);

// Analytics
export const getAnalyticsSummary = (id) => api.get(`/restaurants/${id || requireRestaurantId()}/analytics/summary`);

// Status & Test Mode
export const getStatus = () => api.get(`/status`);
export const getTestModeStatus = () => api.get(`/test-mode/status`);
export const getTestScenarios = () => api.get(`/test-mode/scenarios`);
export const runTestScenario = (id, scenarioId) => 
  api.post(`/test-mode/run-scenario?restaurant_id=${id || requireRestaurantId()}&scenario_id=${scenarioId}`);

// Legacy Demo (for backward compatibility)
export const simulateCall = (id) => api.post(`/demo/simulate-call?restaurant_id=${id || requireRestaurantId()}`);
export const seedData = (id) => api.post(`/demo/seed?restaurant_id=${id || requireRestaurantId()}`);

// Onboarding
export const parseMenu = (data) => api.post(`/onboarding/menu/parse`, data);
export const confirmMenu = (restaurantId, items) => api.post(`/onboarding/menu/confirm?restaurant_id=${restaurantId}`, items);
export const activateRestaurant = (id) => api.post(`/onboarding/activate`, { restaurant_id: id });

export default api;
