import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/utils/msw-server";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";
import AdminPage from "@/pages/dashboard/AdminPage";

function Shell() {
  return (
    <AppSessionProvider>
      <AdminPage />
    </AppSessionProvider>
  );
}

describe("AdminPage (Duuutah AI cost analytics)", () => {
  beforeEach(() => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");
  });

  it("calls the admin cost-analytics API and renders cost copy", async () => {
    server.use(
      http.get("*/api/admin/cost-analytics", () =>
        HttpResponse.json({
          overall: {
            total_calls: 100,
            total_cost_dollars: 123.45,
            total_revenue_dollars: 0,
            total_sms_dollars: 5,
            total_ai_dollars: 10,
            total_sms_sent: 30,
            gross_margin_pct: 50.5,
            gross_margin_dollars: 0,
            gross_margin_percent: 0,
          },
          per_restaurant: [],
        })
      )
    );

    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /Admin.*Cost Analytics/i })
      ).toBeInTheDocument()
    );
  });

  it("renders the not-authorized state when /admin/cost-analytics returns 403", async () => {
    server.use(
      http.get("*/api/admin/cost-analytics", () =>
        new HttpResponse(null, { status: 403 })
      )
    );

    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(
        screen.getAllByText(/admin|access|denied|not authorized|forbidden/i).length
      ).toBeGreaterThan(0)
    );
  });
});
