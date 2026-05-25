import { describe, it, expect, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";
import BillingPage from "@/pages/dashboard/BillingPage";

function Shell() {
  return (
    <AppSessionProvider>
      <BillingPage />
    </AppSessionProvider>
  );
}

describe("BillingPage", () => {
  beforeEach(() => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");
  });

  it("renders the billing screen for the active Duuutah AI restaurant", async () => {
    renderWithProviders(<Shell />);
    // Plan tier copy or upgrade copy should appear
    await waitFor(() =>
      expect(
        screen.getAllByText(/starter|pro|plan|billing|invoice/i).length
      ).toBeGreaterThan(0)
    );
  });

  it("shows the Starter and Pro plan options", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() => {
      expect(screen.getAllByText(/Starter/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/^Pro$/i).length).toBeGreaterThan(0);
    });
  });
});
