import { describe, it, expect, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";
import AILearningPage from "@/pages/dashboard/AILearningPage";

function Shell() {
  return (
    <AppSessionProvider>
      <AILearningPage />
    </AppSessionProvider>
  );
}

describe("AILearningPage", () => {
  beforeEach(() => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");
  });

  it("renders the AI Learning heading", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { level: 1, name: /^AI Learning$/i })
      ).toBeInTheDocument()
    );
  });

  it("shows the upsell card on the STARTER plan", async () => {
    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.getByText(/Upgrade to Pro/i)).toBeInTheDocument()
    );
  });
});
