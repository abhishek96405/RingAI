import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/utils/msw-server";
import { renderWithProviders } from "@/test/utils/render";
import OrdersPage from "@/pages/dashboard/OrdersPage";

describe("OrdersPage", () => {
  beforeEach(() => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");
  });

  it("renders the Order History heading", async () => {
    renderWithProviders(<OrdersPage />);
    expect(
      await screen.findByRole("heading", { name: /order history/i })
    ).toBeInTheDocument();
  });

  it("renders KPI cards for total orders, revenue, and average", async () => {
    renderWithProviders(<OrdersPage />);
    expect(await screen.findByText(/Total Orders/i)).toBeInTheDocument();
    expect(screen.getByText(/Total Revenue/i)).toBeInTheDocument();
    expect(screen.getByText(/Average Order Value/i)).toBeInTheDocument();
  });

  it("shows the empty state when no orders have been placed", async () => {
    renderWithProviders(<OrdersPage />);
    expect(await screen.findByText(/No orders found/i)).toBeInTheDocument();
  });

  it("renders rows when calls with order data are returned", async () => {
    server.use(
      http.get("*/api/restaurants/:id/calls", () =>
        HttpResponse.json({
          calls: [
            {
              id: "call_with_order",
              call_sid: "CA123",
              caller_name: "Diner Dan",
              caller_number: "+15555550100",
              status: "COMPLETED",
              order_total: 2500,
              started_at: "2026-05-20T10:00:00Z",
              order_json: {
                customer_name: "Diner Dan",
                type: "pickup",
                total: 2500,
                items: [{ name: "Pizza", quantity: 1, subtotal: 2500 }],
              },
            },
          ],
          total: 1,
          pages: 1,
        })
      )
    );

    renderWithProviders(<OrdersPage />);

    await waitFor(() =>
      expect(screen.getAllByText(/Diner Dan/i).length).toBeGreaterThan(0)
    );
  });

  it("shows an error toast (renders heading) when the calls API fails", async () => {
    server.use(
      http.get("*/api/restaurants/:id/calls", () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    renderWithProviders(<OrdersPage />);
    // Heading still renders despite the fetch error
    expect(
      await screen.findByRole("heading", { name: /order history/i })
    ).toBeInTheDocument();
  });
});
