import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

export const handlers = [
  http.get("*/api/me/bootstrap", () =>
    HttpResponse.json({
      user: { id: "user_test", email: "test@duuutah.ai" },
      memberships: [{ restaurant_id: "tenant_a_restaurant", role: "owner" }],
      restaurants: [
        {
          id: "tenant_a_restaurant",
          name: "Test Restaurant A",
          business_type: "restaurant",
          is_active: true,
          plan: "STARTER",
        },
      ],
      active_restaurant: {
        id: "tenant_a_restaurant",
        name: "Test Restaurant A",
        business_type: "restaurant",
        is_active: true,
        plan: "STARTER",
      },
      onboarding_complete: true,
    })
  ),

  http.post("*/api/me/select-restaurant", () =>
    HttpResponse.json({ ok: true })
  ),

  http.get("*/api/restaurants/:id", ({ params }) =>
    HttpResponse.json({
      id: params.id,
      name: "Test Restaurant A",
      business_type: "restaurant",
      is_active: true,
      plan: "STARTER",
    })
  ),

  http.put("*/api/restaurants/:id", () => HttpResponse.json({ ok: true })),
  http.post("*/api/restaurants", () =>
    HttpResponse.json({ id: "new_restaurant_id", name: "New Restaurant" })
  ),

  http.get("*/api/restaurants/:id/config", () =>
    HttpResponse.json({
      business_type: "restaurant",
      operating_hours: {
        monday: { closed: false, open: "09:00", close: "21:00" },
        tuesday: { closed: false, open: "09:00", close: "21:00" },
        wednesday: { closed: false, open: "09:00", close: "21:00" },
        thursday: { closed: false, open: "09:00", close: "21:00" },
        friday: { closed: false, open: "09:00", close: "22:00" },
        saturday: { closed: false, open: "09:00", close: "22:00" },
        sunday: { closed: false, open: "09:00", close: "20:00" },
      },
      business_rules: [],
      escalation_rules: [],
    })
  ),

  http.put("*/api/restaurants/:id/config", () => HttpResponse.json({ ok: true })),

  http.get("*/api/restaurants/:id/menu", () => HttpResponse.json([])),
  http.post("*/api/restaurants/:id/menu", () =>
    HttpResponse.json({ id: "menu_item_test", name: "Test Item" })
  ),
  http.put("*/api/menu/:itemId", () => HttpResponse.json({ ok: true })),
  http.delete("*/api/menu/:itemId", () => HttpResponse.json({ ok: true })),
  http.patch("*/api/menu/:itemId/toggle", () => HttpResponse.json({ ok: true })),

  http.get("*/api/restaurants/:id/calls", () =>
    HttpResponse.json({ calls: [], total: 0, pages: 1 })
  ),
  http.get("*/api/calls/:callId", ({ params }) =>
    HttpResponse.json({
      id: params.callId,
      caller_name: "Test Caller",
      caller_number: "+15555550100",
      status: "COMPLETED",
      duration_seconds: 60,
      transcript: [],
    })
  ),
  http.post("*/api/calls/:callId/analyse", () =>
    HttpResponse.json({ ok: true })
  ),

  http.get("*/api/restaurants/:id/analytics/summary", () =>
    HttpResponse.json({
      total_calls: 0,
      calls_this_week: 0,
      calls_this_month: 0,
      revenue_this_week: 0,
      revenue_this_month: 0,
      avg_quality_score: 0,
      ai_containment_rate: 0,
      escalated_calls: 0,
      recent_calls: [],
      top_items: [],
      daily_call_data: [],
      monthly_call_data: [],
      hourly_distribution: [],
    })
  ),

  http.get("*/api/restaurants/:id/analytics/export", () =>
    HttpResponse.text("col1,col2\nval1,val2", {
      headers: { "Content-Type": "text/csv" },
    })
  ),

  http.get("*/api/restaurants/:id/services", () => HttpResponse.json([])),
  http.post("*/api/restaurants/:id/services", () =>
    HttpResponse.json({ id: "svc_test", name: "Test Service" })
  ),
  http.put("*/api/services/:id", () => HttpResponse.json({ ok: true })),
  http.delete("*/api/services/:id", () => HttpResponse.json({ ok: true })),

  http.get("*/api/restaurants/:id/appointments", () => HttpResponse.json([])),
  http.get("*/api/appointments/:id", ({ params }) =>
    HttpResponse.json({ id: params.id })
  ),
  http.patch("*/api/appointments/:id/cancel", () =>
    HttpResponse.json({ ok: true })
  ),
  http.post("*/api/restaurants/:id/calendar/book", () =>
    HttpResponse.json({ id: "appt_new" })
  ),
  http.get("*/api/restaurants/:id/blocked-slots", () => HttpResponse.json([])),
  http.post("*/api/restaurants/:id/blocked-slots", () =>
    HttpResponse.json({ id: "block_new" })
  ),
  http.delete("*/api/restaurants/:id/blocked-slots/:slotId", () =>
    HttpResponse.json({ ok: true })
  ),
  http.get("*/api/restaurants/:id/available-slots", () =>
    HttpResponse.json([])
  ),
  http.get("*/api/restaurants/:id/calendar/status", () =>
    HttpResponse.json({ connected: false })
  ),
  http.get("*/api/calendar/google/connect", () =>
    HttpResponse.json({ url: "https://example.com/oauth" })
  ),
  http.delete("*/api/restaurants/:id/calendar/disconnect", () =>
    HttpResponse.json({ ok: true })
  ),
  http.get("*/api/restaurants/:id/calendar/availability", () =>
    HttpResponse.json([])
  ),

  http.get("*/api/restaurants/:id/reservations", () => HttpResponse.json([])),
  http.patch("*/api/restaurants/:id/reservations/:rid", () =>
    HttpResponse.json({ ok: true })
  ),
  http.delete("*/api/restaurants/:id/reservations/:rid", () =>
    HttpResponse.json({ ok: true })
  ),
  http.get("*/api/restaurants/:id/reservations/slots", () =>
    HttpResponse.json([])
  ),

  http.get("*/api/restaurants/:id/modifier-groups", () => HttpResponse.json([])),
  http.post("*/api/restaurants/:id/modifier-groups", () =>
    HttpResponse.json({ id: "mod_grp_test" })
  ),
  http.put("*/api/modifier-groups/:groupId", () => HttpResponse.json({ ok: true })),
  http.delete("*/api/modifier-groups/:groupId", () =>
    HttpResponse.json({ ok: true })
  ),
  http.put("*/api/menu/:itemId/modifier-assignments", () =>
    HttpResponse.json({ ok: true })
  ),

  http.get("*/api/status", () =>
    HttpResponse.json({ ok: true, service: "duuutah-ai" })
  ),
  http.get("*/api/test-mode/status", () =>
    HttpResponse.json({ enabled: false })
  ),
  http.get("*/api/test-mode/scenarios", () => HttpResponse.json([])),
  http.post("*/api/test-mode/run-scenario", () =>
    HttpResponse.json({ ok: true })
  ),

  http.post("*/api/demo/simulate-call", () => HttpResponse.json({ ok: true })),
  http.post("*/api/demo/seed", () => HttpResponse.json({ ok: true })),

  http.post("*/api/onboarding/menu/parse", () =>
    HttpResponse.json({ items: [] })
  ),
  http.post("*/api/onboarding/menu/confirm", () =>
    HttpResponse.json({ ok: true })
  ),
  http.post("*/api/onboarding/activate", () => HttpResponse.json({ ok: true })),

  http.post("*/api/billing/create-checkout-session", () =>
    HttpResponse.json({ url: "https://checkout.stripe.test/abc" })
  ),
  http.post("*/api/billing/portal", () =>
    HttpResponse.json({ url: "https://billing.stripe.test/portal" })
  ),
  http.get("*/api/restaurants/:id/plan-features", () =>
    HttpResponse.json({ plan: "STARTER", features: [] })
  ),
  http.get("*/api/billing/invoices", () => HttpResponse.json([])),

  http.get("*/api/integrations/square/connect", () =>
    HttpResponse.json({ url: "https://square.test/oauth" })
  ),
  http.get("*/api/telnyx/numbers/status", () =>
    HttpResponse.json({ provisioned: false })
  ),
  http.post("*/api/telnyx/numbers/provision", () =>
    HttpResponse.json({ phone_number: "+15555550100" })
  ),
  http.post("*/api/telnyx/numbers/assign-existing", () =>
    HttpResponse.json({ ok: true })
  ),

  http.get("*/api/integrations/stripe/connect", () =>
    HttpResponse.json({ url: "https://stripe.test/oauth" })
  ),
  http.get("*/api/integrations/stripe/status", () =>
    HttpResponse.json({ connected: false })
  ),
  http.post("*/api/integrations/stripe/disconnect", () =>
    HttpResponse.json({ ok: true })
  ),
  http.post("*/api/restaurants/:id/orders/:callSid/refund", () =>
    HttpResponse.json({ ok: true })
  ),

  http.get("*/api/voice-preview/:voice", () =>
    new HttpResponse(new Blob([new Uint8Array([1, 2, 3])]), {
      headers: { "Content-Type": "audio/mpeg" },
    })
  ),

  http.get("*/api/admin/cost-analytics", () =>
    HttpResponse.json({
      total_cost: 0,
      total_calls: 0,
      total_sms: 0,
      total_ai_tokens: 0,
      daily_breakdown: [],
    })
  ),

  http.post("*/api/restaurants/:id/pos/sync", () =>
    HttpResponse.json({ ok: true })
  ),
  http.post("*/api/restaurants/:id/pos/credentials", () =>
    HttpResponse.json({ ok: true })
  ),
  http.post("*/api/restaurants/:id/pos/test", () =>
    HttpResponse.json({ success: true })
  ),

  http.get("*/api/restaurants/:id/learning/stats", () =>
    HttpResponse.json({
      total_calls_processed: 0,
      aliases_learned: 0,
      calls_flagged: 0,
      last_processed: null,
    })
  ),
  http.get("*/api/restaurants/:id/learning/aliases", () =>
    HttpResponse.json({ aliases: [] })
  ),
  http.get("*/api/restaurants/:id/learning/suggestions", () =>
    HttpResponse.json({ pending_aliases: [], suggested_rules: [] })
  ),
  http.post("*/api/restaurants/:id/learning/aliases/:aliasId/approve", () =>
    HttpResponse.json({ ok: true })
  ),
  http.post("*/api/restaurants/:id/learning/aliases/:aliasId/reject", () =>
    HttpResponse.json({ ok: true })
  ),
  http.get("*/api/restaurants/:id/learning/flagged-calls", () =>
    HttpResponse.json({ flagged_calls: [] })
  ),
];

export const server = setupServer(...handlers);
