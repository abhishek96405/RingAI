import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/utils/msw-server";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";
import ReservationsPage from "@/pages/dashboard/ReservationsPage";

function Shell() {
  return (
    <AppSessionProvider>
      <ReservationsPage />
    </AppSessionProvider>
  );
}

const PRO_BOOTSTRAP_HANDLER = http.get("*/api/me/bootstrap", () =>
  HttpResponse.json({
    user: { id: "user_test" },
    memberships: [{ restaurant_id: "tenant_a_restaurant", role: "owner" }],
    restaurants: [
      {
        id: "tenant_a_restaurant",
        name: "Test Restaurant A",
        business_type: "restaurant",
        is_active: true,
        plan: "PRO",
      },
    ],
    active_restaurant: {
      id: "tenant_a_restaurant",
      name: "Test Restaurant A",
      business_type: "restaurant",
      is_active: true,
      plan: "PRO",
    },
    onboarding_complete: true,
  })
);

describe("ReservationsPage", () => {
  beforeEach(() => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");
  });

  it("renders the Pro upsell when the restaurant is on a STARTER plan", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /AI Table Reservations/i })
      ).toBeInTheDocument()
    );
    expect(screen.getByText(/Upgrade to Pro/i)).toBeInTheDocument();
  });

  it("renders the reservations panel on PRO plan", async () => {
    server.use(PRO_BOOTSTRAP_HANDLER);

    renderWithProviders(<Shell />);
    // Wait for the upsell to disappear (bootstrap returns PRO plan)
    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: /AI Table Reservations/i })
      ).not.toBeInTheDocument()
    );
    expect(screen.getAllByText(/reservation/i).length).toBeGreaterThan(0);
  });

  it("treats a lowercase 'pro' plan as Pro (case-insensitive)", async () => {
    server.use(
      http.get("*/api/me/bootstrap", () =>
        HttpResponse.json({
          user: { id: "user_test" },
          memberships: [{ restaurant_id: "tenant_a_restaurant", role: "owner" }],
          restaurants: [
            { id: "tenant_a_restaurant", name: "Test Restaurant A", business_type: "restaurant", is_active: true, plan: "pro" },
          ],
          active_restaurant: { id: "tenant_a_restaurant", name: "Test Restaurant A", business_type: "restaurant", is_active: true, plan: "pro" },
          onboarding_complete: true,
        })
      )
    );
    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: /AI Table Reservations/i })).not.toBeInTheDocument()
    );
    expect(screen.getAllByText(/reservation/i).length).toBeGreaterThan(0);
  });

  it("renders reservations when the API returns rows", async () => {
    server.use(
      PRO_BOOTSTRAP_HANDLER,
      http.get("*/api/restaurants/:id/reservations", () =>
        HttpResponse.json({
          reservations: [
            {
              id: "res_1",
              customer_name: "Diner Daria",
              customer_phone: "+15555550101",
              party_size: 4,
              reservation_date: "2026-06-02",
              reservation_time: "19:00",
              status: "confirmed",
            },
          ],
        })
      )
    );

    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.getByText(/Diner Daria/i)).toBeInTheDocument()
    );
  });

  it("does not crash when the reservations API errors on PRO", async () => {
    server.use(
      PRO_BOOTSTRAP_HANDLER,
      http.get("*/api/restaurants/:id/reservations", () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.getAllByText(/reservation/i).length).toBeGreaterThan(0)
    );
  });
});
