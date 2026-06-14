import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/utils/msw-server";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";
import DashboardHome from "@/pages/dashboard/DashboardHome";
import { SAMPLE_ANALYTICS_SUMMARY } from "@/test/utils/fixtures";

function Shell() {
  return (
    <AppSessionProvider>
      <DashboardHome />
    </AppSessionProvider>
  );
}

describe("DashboardHome page (Duuutah AI overview)", () => {
  beforeEach(() => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");
  });

  it("renders the dashboard heading and weekly/monthly toggle", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /^dashboard$/i })).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: /weekly/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /monthly/i })).toBeInTheDocument();
  });

  it("shows the 'no real call data' card when total_calls === 0", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.getByText(/No real call data yet/i)).toBeInTheDocument()
    );
  });

  it("renders KPI stat cards when analytics return real numbers", async () => {
    server.use(
      http.get("*/api/restaurants/:id/analytics/summary", () =>
        HttpResponse.json(SAMPLE_ANALYTICS_SUMMARY)
      )
    );

    renderWithProviders(<Shell />);
    await waitFor(() => {
      expect(screen.getByText(/Total Calls This Week/i)).toBeInTheDocument();
      expect(screen.getByText(/Revenue This Week/i)).toBeInTheDocument();
      expect(screen.getByText(/Avg Quality Score/i)).toBeInTheDocument();
      expect(screen.getByText(/AI Containment Rate/i)).toBeInTheDocument();
    });
  });

  it("renders recent calls when present in the analytics payload", async () => {
    server.use(
      http.get("*/api/restaurants/:id/analytics/summary", () =>
        HttpResponse.json(SAMPLE_ANALYTICS_SUMMARY)
      )
    );

    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.getByText(/Alice Customer/i)).toBeInTheDocument()
    );
  });

  it("renders 'No order data yet' when top_items is empty", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.getByText(/No order data yet/i)).toBeInTheDocument()
    );
  });

  it("recovers (renders the layout) when the analytics request fails", async () => {
    server.use(
      http.get("*/api/restaurants/:id/analytics/summary", () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    renderWithProviders(<Shell />);
    // Dashboard heading still renders; toast error is fired internally
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /^dashboard$/i })).toBeInTheDocument()
    );
  });

  it("offers a CSV export button", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /export/i })
      ).toBeInTheDocument()
    );
  });
});
