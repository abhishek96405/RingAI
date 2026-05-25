import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/utils/msw-server";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";
import ServicesPage from "@/pages/dashboard/ServicesPage";

function Shell() {
  return (
    <AppSessionProvider>
      <ServicesPage />
    </AppSessionProvider>
  );
}

describe("ServicesPage", () => {
  beforeEach(() => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_clinic");
  });

  it("renders a Services heading", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(
        screen.getAllByText(/services/i).length
      ).toBeGreaterThan(0)
    );
  });

  it("renders rows when the API returns service items", async () => {
    server.use(
      http.get("*/api/restaurants/:id/services", () =>
        HttpResponse.json([
          {
            id: "svc_1",
            name: "Cleaning",
            description: "Deep clean",
            duration_minutes: 60,
            price_cents: 8500,
          },
        ])
      )
    );

    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.getByText(/Cleaning/i)).toBeInTheDocument()
    );
  });

  it("survives an API failure", async () => {
    server.use(
      http.get("*/api/restaurants/:id/services", () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(
        screen.getAllByText(/services/i).length
      ).toBeGreaterThan(0)
    );
  });
});
