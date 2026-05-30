import { describe, it, expect, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";
import SettingsPage from "@/pages/dashboard/settings/SettingsPage";

function Shell() {
  return (
    <AppSessionProvider>
      <SettingsPage />
    </AppSessionProvider>
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");
  });

  it("renders the Business tab by default", async () => {
    renderWithProviders(<Shell />);
    expect(
      await screen.findByRole("tab", { name: /business/i })
    ).toBeInTheDocument();
  });

  it("renders Hours, Voice & AI, and Rules tabs", async () => {
    renderWithProviders(<Shell />);
    expect(await screen.findByRole("tab", { name: /hours/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /voice & ai/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /rules/i })).toBeInTheDocument();
  });

  it("renders the Phone & Forwarding tab", async () => {
    renderWithProviders(<Shell />);
    expect(
      await screen.findByRole("tab", { name: /phone & forwarding/i }),
    ).toBeInTheDocument();
  });

  it("includes a Fulfillment tab for restaurant business type", async () => {
    renderWithProviders(<Shell />);
    expect(
      await screen.findByRole("tab", { name: /fulfillment/i })
    ).toBeInTheDocument();
  });

  it("switches to the Hours tab when its tab is clicked", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Shell />);
    await user.click(await screen.findByRole("tab", { name: /hours/i }));

    await waitFor(() => {
      const hoursTab = screen.getByRole("tab", { name: /hours/i });
      expect(hoursTab).toHaveAttribute("data-state", "active");
    });
  });
});
