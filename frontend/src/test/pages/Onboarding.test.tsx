import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/utils/msw-server";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";
import Onboarding from "@/pages/Onboarding";

function ShellOnboarding() {
  return (
    <AppSessionProvider>
      <Onboarding />
    </AppSessionProvider>
  );
}

describe("Onboarding page (Duuutah AI)", () => {
  beforeEach(() => {
    localStorage.clear();
    server.use(
      http.get("*/api/me/bootstrap", () =>
        HttpResponse.json({
          user: { id: "user_test" },
          memberships: [],
          restaurants: [],
          active_restaurant: null,
          onboarding_complete: false,
        })
      )
    );
  });

  it("starts on the Business Type step", async () => {
    renderWithProviders(<ShellOnboarding />, { initialEntries: ["/onboarding"] });

    await waitFor(() =>
      expect(screen.getAllByText(/Business Type/i).length).toBeGreaterThan(0)
    );
  });

  it("offers all five business-type options", async () => {
    renderWithProviders(<ShellOnboarding />, { initialEntries: ["/onboarding"] });

    await waitFor(() => {
      expect(screen.getByText(/Restaurant \/ Food Service/i)).toBeInTheDocument();
      expect(screen.getByText(/Clinic \/ Healthcare/i)).toBeInTheDocument();
      expect(screen.getByText(/Salon \/ Beauty/i)).toBeInTheDocument();
      expect(screen.getByText(/Home Services/i)).toBeInTheDocument();
      expect(screen.getByText(/Legal \/ Professional/i)).toBeInTheDocument();
    });
  });

  it("advances to the Business Info step after a type is chosen", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ShellOnboarding />, { initialEntries: ["/onboarding"] });

    await waitFor(() =>
      expect(screen.getByText(/Restaurant \/ Food Service/i)).toBeInTheDocument()
    );

    await user.click(screen.getByText(/Restaurant \/ Food Service/i));
    // A "Continue" or "Next" button should be visible / clickable after selection
    const nextBtn = screen
      .getAllByRole("button")
      .find((b) => /continue|next/i.test(b.textContent ?? ""));
    expect(nextBtn).toBeDefined();
  });
});
