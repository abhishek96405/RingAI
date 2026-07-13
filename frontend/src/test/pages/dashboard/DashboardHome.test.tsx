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

  it("renders the daily-briefing hero and weekly/monthly toggle", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.getByText(/your daily briefing/i)).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: /weekly/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /monthly/i })).toBeInTheDocument();
  });

  it("shows the empty-state briefing and 'all clear' when there are no calls", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.getByText(/no calls yet this week/i)).toBeInTheDocument()
    );
    expect(screen.getByText(/all clear/i)).toBeInTheDocument();
  });

  it("renders KPI stat cards when analytics return real numbers", async () => {
    server.use(
      http.get("*/api/restaurants/:id/analytics/summary", () =>
        HttpResponse.json(SAMPLE_ANALYTICS_SUMMARY)
      )
    );

    renderWithProviders(<Shell />);
    await waitFor(() => {
      // "Revenue" is also the chart legend label, so match all
      expect(screen.getAllByText(/Revenue/i).length).toBeGreaterThan(0);
      expect(screen.getByText(/Quality/i)).toBeInTheDocument();
      // "handled by AI" also appears in the hero chip, so match all
      expect(screen.getAllByText(/Handled by AI/i).length).toBeGreaterThan(0);
      expect(screen.getByText(/Escalated/i)).toBeInTheDocument();
    });
  });

  it("summarizes call volume and escalations in the briefing", async () => {
    server.use(
      http.get("*/api/restaurants/:id/analytics/summary", () =>
        HttpResponse.json(SAMPLE_ANALYTICS_SUMMARY)
      )
    );

    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.getByText(/Duuutah answered 18 calls this week/i)).toBeInTheDocument()
    );
    // 4 escalated calls surface in the "Needs you" section
    expect(
      screen.getByText(/needed a human this week/i)
    ).toBeInTheDocument();
  });

  it("renders top items when present in the analytics payload", async () => {
    server.use(
      http.get("*/api/restaurants/:id/analytics/summary", () =>
        HttpResponse.json(SAMPLE_ANALYTICS_SUMMARY)
      )
    );

    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.getByText(/Margherita Pizza/i)).toBeInTheDocument()
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
    // Briefing hero still renders; toast error is fired internally
    await waitFor(() =>
      expect(screen.getByText(/your daily briefing/i)).toBeInTheDocument()
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
