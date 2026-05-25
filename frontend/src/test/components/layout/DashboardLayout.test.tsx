import { describe, it, expect, beforeEach, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { server } from "@/test/utils/msw-server";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";
import DashboardLayout from "@/components/layout/DashboardLayout";

// Skip WebSocket connections in layout tests; the WS hook is tested in isolation
class NoopWebSocket {
  readyState = 1;
  onopen: (() => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  send = vi.fn();
  close = vi.fn();
  constructor(public url: string) {}
}

function DashboardShell({ path = "/dashboard" }: { path?: string }) {
  return (
    <AppSessionProvider>
      <Routes>
        <Route path="/dashboard" element={<DashboardLayout />}>
          <Route index element={<div data-testid="outlet">Dashboard outlet</div>} />
          <Route
            path="calls"
            element={<div data-testid="outlet-calls">Calls outlet</div>}
          />
        </Route>
      </Routes>
    </AppSessionProvider>
  );
}

describe("DashboardLayout", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("WebSocket", NoopWebSocket as unknown as typeof WebSocket);
  });

  it("renders the Duuutah AI brand and sidebar nav", async () => {
    renderWithProviders(<DashboardShell />, { initialEntries: ["/dashboard"] });

    await waitFor(() =>
      expect(screen.getByTestId("outlet")).toBeInTheDocument()
    );
    expect(screen.getAllByAltText(/Duuutah AI/i).length).toBeGreaterThan(0);
    // Restaurant nav links visible by default (business_type=restaurant)
    expect(screen.getAllByText(/^Dashboard$/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^Calls$/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^Menu$/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^Orders$/i).length).toBeGreaterThan(0);
  });

  it("shows appointment-business nav for clinic/salon/home_services", async () => {
    server.use(
      http.get("*/api/restaurants/:id/config", () =>
        HttpResponse.json({
          business_type: "clinic",
          operating_hours: {},
        })
      )
    );

    renderWithProviders(<DashboardShell />, { initialEntries: ["/dashboard"] });

    await waitFor(() =>
      expect(screen.getByTestId("outlet")).toBeInTheDocument()
    );

    await waitFor(() => {
      expect(screen.getAllByText(/Services/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Appointments/i).length).toBeGreaterThan(0);
    });
  });

  it("displays the activeRestaurant name in the header", async () => {
    renderWithProviders(<DashboardShell />, { initialEntries: ["/dashboard"] });

    await waitFor(() =>
      expect(screen.getByText(/Test Restaurant A/i)).toBeInTheDocument()
    );
  });

  it("shows a notifications popover trigger with zero unread by default", async () => {
    renderWithProviders(<DashboardShell />, { initialEntries: ["/dashboard"] });

    await waitFor(() =>
      expect(screen.getByTestId("notifications-btn")).toBeInTheDocument()
    );
    // No unread badge when notifications are empty
    expect(
      screen.getByTestId("notifications-btn").querySelector("span")
    ).toBeNull();
  });

  it("opens the notifications panel when the bell is clicked", async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardShell />, { initialEntries: ["/dashboard"] });

    await waitFor(() =>
      expect(screen.getByTestId("notifications-btn")).toBeInTheDocument()
    );

    await user.click(screen.getByTestId("notifications-btn"));

    await waitFor(() =>
      expect(screen.getByText(/No notifications/i)).toBeInTheDocument()
    );
  });

  it("renders a past-due billing banner when restaurant.billing_status === 'past_due'", async () => {
    server.use(
      http.get("*/api/me/bootstrap", () =>
        HttpResponse.json({
          memberships: [{ restaurant_id: "r1" }],
          restaurants: [
            {
              id: "r1",
              name: "Late Payer",
              business_type: "restaurant",
              is_active: true,
              billing_status: "past_due",
            },
          ],
          active_restaurant: {
            id: "r1",
            name: "Late Payer",
            business_type: "restaurant",
            is_active: true,
            billing_status: "past_due",
          },
          onboarding_complete: true,
        })
      )
    );

    renderWithProviders(<DashboardShell />, { initialEntries: ["/dashboard"] });

    await waitFor(() =>
      expect(screen.getByText(/payment failed/i)).toBeInTheDocument()
    );
    expect(
      screen.getByRole("link", { name: /Fix now/i })
    ).toHaveAttribute("href", "/dashboard/billing");
  });
});
