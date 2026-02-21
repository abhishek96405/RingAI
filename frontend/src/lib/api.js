import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Default restaurant ID for the demo
const DEMO_RESTAURANT_ID = "demo-restaurant-001";

export const api = axios.create({
  baseURL: API,
  headers: { "Content-Type": "application/json" },
});

export const getRestaurantId = () => DEMO_RESTAURANT_ID;

// Restaurant
export const getRestaurant = (id) => api.get(`/restaurants/${id || DEMO_RESTAURANT_ID}`);
export const updateRestaurant = (id, data) => api.put(`/restaurants/${id || DEMO_RESTAURANT_ID}`, data);

// Config
export const getConfig = (id) => api.get(`/restaurants/${id || DEMO_RESTAURANT_ID}/config`);
export const updateConfig = (id, data) => api.put(`/restaurants/${id || DEMO_RESTAURANT_ID}/config`, data);

// Menu
export const getMenuItems = (id, category) => {
  const params = category ? { category } : {};
  return api.get(`/restaurants/${id || DEMO_RESTAURANT_ID}/menu`, { params });
};
export const createMenuItem = (id, data) => api.post(`/restaurants/${id || DEMO_RESTAURANT_ID}/menu`, data);
export const updateMenuItem = (itemId, data) => api.put(`/menu/${itemId}`, data);
export const deleteMenuItem = (itemId) => api.delete(`/menu/${itemId}`);
export const toggleMenuItem = (itemId) => api.patch(`/menu/${itemId}/toggle`);

// Calls
export const getCalls = (id, params) => api.get(`/restaurants/${id || DEMO_RESTAURANT_ID}/calls`, { params });
export const getCall = (callId) => api.get(`/calls/${callId}`);

// Analytics
export const getAnalyticsSummary = (id) => api.get(`/restaurants/${id || DEMO_RESTAURANT_ID}/analytics/summary`);

// Demo
export const simulateCall = (id) => api.post(`/demo/simulate-call?restaurant_id=${id || DEMO_RESTAURANT_ID}`);
export const seedData = (id) => api.post(`/demo/seed?restaurant_id=${id || DEMO_RESTAURANT_ID}`);

// Onboarding
export const parseMenu = (data) => api.post(`/onboarding/menu/parse`, data);
export const activateRestaurant = (id) => api.post(`/onboarding/activate`, { restaurant_id: id || DEMO_RESTAURANT_ID });

export default api;
