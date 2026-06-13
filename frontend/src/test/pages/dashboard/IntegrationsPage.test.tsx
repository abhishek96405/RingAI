import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";

// Mock the page's data-source helpers so we can drive connected-state and the
// calendar gate. Everything else (bootstrap axios, storage helpers) stays real
// via the actual spread — same pattern as CloverCallbackPage.test.tsx.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getRestaurant: vi.fn(),
    getCalendarStatus: vi.fn(),
  };
});

import IntegrationsPage from "@/pages/dashboard/IntegrationsPage";
import { getRestaurant, getCalendarStatus } from "@/lib/api";

function Shell() {
  return (
    <AppSessionProvider>
      <IntegrationsPage />
    </AppSessionProvider>
  );
}

function mockRestaurant(overrides: Record<string, unknown> = {}) {
  vi.mocked(getRestaurant).mockResolvedValue({
    data: {
      id: "tenant_a_restaurant",
      business_type: "restaurant",
      square_connected: false,
      clover_connected: false,
      ...overrides,
    },
  } as never);
}

describe("IntegrationsPage", () => {
  beforeEach(() => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");
    vi.mocked(getRestaurant).mockReset();
    vi.mocked(getCalendarStatus).mockReset();
    vi.mocked(getCalendarStatus).mockResolvedValue({ data: { connected: false } } as never);
    mockRestaurant();
  });

  it("renders the POS connect section", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() => expect(screen.getByText(/Connect your POS/i)).toBeInTheDocument());
    expect(screen.getByText("Square")).toBeInTheDocument();
    expect(screen.getByText("Clover")).toBeInTheDocument();
    expect(screen.getByText("Toast")).toBeInTheDocument();
  });

  // ── Calendar gate (Part C): shown unless business_type === "restaurant" ──
  it("hides the Google Calendar card for restaurants", async () => {
    mockRestaurant({ business_type: "restaurant" });
    renderWithProviders(<Shell />);
    await waitFor(() => expect(screen.getByText(/Connect your POS/i)).toBeInTheDocument());
    expect(screen.queryByText(/Google Calendar/i)).not.toBeInTheDocument();
  });

  it("shows the Google Calendar card for salons", async () => {
    mockRestaurant({ business_type: "salon" });
    renderWithProviders(<Shell />);
    await waitFor(() => expect(screen.getByRole("heading", { name: /Google Calendar/i })).toBeInTheDocument());
  });

  it("shows the Google Calendar card for a non-restaurant non-salon vertical (clinic)", async () => {
    mockRestaurant({ business_type: "clinic" });
    renderWithProviders(<Shell />);
    await waitFor(() => expect(screen.getByRole("heading", { name: /Google Calendar/i })).toBeInTheDocument());
  });

  // ── Square connected-state (Part D) ──
  it("shows a Connected badge for Square when square_connected is true", async () => {
    mockRestaurant({ square_connected: true });
    renderWithProviders(<Shell />);
    await waitFor(() => expect(screen.getByText(/Connect your POS/i)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /Connect with Square/i })).not.toBeInTheDocument();
    expect(screen.getAllByText(/Connected/i).length).toBeGreaterThan(0);
  });

  it("shows a Connect with Square button when square_connected is false", async () => {
    mockRestaurant({ square_connected: false });
    renderWithProviders(<Shell />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Connect with Square/i })).toBeInTheDocument());
  });

  // ── Clover connected-state (Part D) ──
  it("shows a Connected badge for Clover when clover_connected is true", async () => {
    mockRestaurant({ clover_connected: true });
    renderWithProviders(<Shell />);
    await waitFor(() => expect(screen.getByText(/Connect your POS/i)).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /Connect with Clover/i })).not.toBeInTheDocument();
    expect(screen.getAllByText(/Connected/i).length).toBeGreaterThan(0);
  });

  it("shows a Connect with Clover button when clover_connected is false", async () => {
    mockRestaurant({ clover_connected: false });
    renderWithProviders(<Shell />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Connect with Clover/i })).toBeInTheDocument());
  });

  // ── Toast (Part D) ──
  it("renders the Toast button as disabled (coming soon)", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() => expect(screen.getByText(/Connect your POS/i)).toBeInTheDocument());
    const toastBtn = screen.getByRole("button", { name: /Coming soon/i });
    expect(toastBtn).toBeDisabled();
  });

  // ── Manual accordion (Part D, Section 2) ──
  it("keeps the manual credentials form collapsed by default and expands on toggle", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() => expect(screen.getByText(/Connect your POS/i)).toBeInTheDocument());

    const toggle = screen.getByRole("button", { name: /Advanced: enter credentials manually/i });
    // Collapsed: the Save Credentials button is not yet in the DOM.
    expect(screen.queryByRole("button", { name: /Save Credentials/i })).not.toBeInTheDocument();

    fireEvent.click(toggle);

    await waitFor(() => expect(screen.getByRole("button", { name: /Save Credentials/i })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Test Connection/i })).toBeInTheDocument();
  });
});
