export const TENANT_A_RESTAURANT = {
  id: "tenant_a_restaurant",
  name: "Test Restaurant A",
  business_type: "restaurant" as const,
  is_active: true,
  plan: "STARTER" as const,
  cuisine_type: "italian",
};

export const TENANT_B_RESTAURANT = {
  id: "tenant_b_restaurant",
  name: "Test Restaurant B",
  business_type: "restaurant" as const,
  is_active: true,
  plan: "PRO" as const,
};

export const APPOINTMENT_BUSINESS_RESTAURANT = {
  id: "tenant_clinic",
  name: "Sunrise Clinic",
  business_type: "clinic" as const,
  is_active: true,
  plan: "PRO" as const,
};

export const SAMPLE_BOOTSTRAP = {
  user: { id: "user_test", email: "test@duuutah.ai" },
  memberships: [{ restaurant_id: TENANT_A_RESTAURANT.id, role: "owner" }],
  restaurants: [TENANT_A_RESTAURANT],
  active_restaurant: TENANT_A_RESTAURANT,
  onboarding_complete: true,
};

export const SAMPLE_CALL = {
  id: "call_test_1",
  restaurant_id: TENANT_A_RESTAURANT.id,
  caller_name: "Alice Customer",
  caller_number: "+15555550100",
  duration_seconds: 120,
  status: "COMPLETED",
  started_at: "2026-01-15T10:00:00Z",
  transcript: [
    { role: "ai", text: "Hi, thanks for calling Test Restaurant!", timestamp: "00:00" },
    { role: "customer", text: "I'd like to order a pizza", timestamp: "00:02" },
  ],
  order_json: {
    items: [{ name: "Margherita", quantity: 1, subtotal: 1500 }],
    total: 1500,
    type: "pickup",
  },
  order_total: 1500,
  quality_score: 92,
  contained_by_ai: true,
  escalated_to_human: false,
  analysis_json: {
    summary: "Order completed smoothly.",
    highlights: ["Polite", "Clear"],
    issues: [],
  },
};

export const SAMPLE_MENU_ITEM = {
  id: "menu_item_1",
  restaurant_id: TENANT_A_RESTAURANT.id,
  name: "Margherita Pizza",
  description: "Classic pizza with fresh basil",
  price_cents: 1500,
  category: "Pizza",
  is_active: true,
};

export const SAMPLE_SERVICE = {
  id: "svc_1",
  name: "Standard Cleaning",
  description: "60 minute professional cleaning",
  duration_minutes: 60,
  price_cents: 8500,
};

export const SAMPLE_APPOINTMENT = {
  id: "appt_1",
  customer_name: "Bob Patient",
  customer_phone: "+15555550199",
  customer_email: "bob@example.com",
  service_name: "Standard Cleaning",
  appointment_date: "2026-06-01",
  start_time: "10:00",
  end_time: "11:00",
  status: "CONFIRMED",
};

export const SAMPLE_RESERVATION = {
  id: "res_1",
  customer_name: "Carol Diner",
  customer_phone: "+15555550101",
  party_size: 4,
  reservation_date: "2026-06-02",
  reservation_time: "19:00",
  status: "CONFIRMED",
};

export const SAMPLE_ANALYTICS_SUMMARY = {
  total_calls: 42,
  calls_this_week: 18,
  calls_this_month: 42,
  revenue_this_week: 25000,
  revenue_this_month: 75000,
  avg_quality_score: 88,
  ai_containment_rate: 81,
  escalated_calls: 4,
  recent_calls: [SAMPLE_CALL],
  top_items: [{ name: "Margherita Pizza", count: 12 }],
  daily_call_data: [
    { label: "Mon", calls: 3, revenue: 4500 },
    { label: "Tue", calls: 5, revenue: 7500 },
  ],
  monthly_call_data: [],
  hourly_distribution: [
    { hour: "10", calls: 2 },
    { hour: "12", calls: 5 },
  ],
};
