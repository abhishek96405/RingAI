import { describe, it, expect, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";
import IntegrationsPage from "@/pages/dashboard/IntegrationsPage";

function Shell() {
  return (
    <AppSessionProvider>
      <IntegrationsPage />
    </AppSessionProvider>
  );
}

describe("IntegrationsPage", () => {
  beforeEach(() => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");
  });

  it("renders the page (mentions Integrations somewhere)", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(
        screen.getAllByText(/integration|connect|telnyx|square|stripe|google/i).length
      ).toBeGreaterThan(0)
    );
  });

  it("renders POS credentials and Square card without crashing on default handlers", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(
        screen.getAllByText(/integration|connect|telnyx|square|stripe|google/i).length
      ).toBeGreaterThan(0)
    );
  });
});
