import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/utils/msw-server";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";
import MenuPage from "@/pages/dashboard/MenuPage";

function Shell() {
  return (
    <AppSessionProvider>
      <MenuPage />
    </AppSessionProvider>
  );
}

describe("MenuPage", () => {
  beforeEach(() => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");
  });

  it("renders the Menu Items / Modifier Library tabs", async () => {
    renderWithProviders(<Shell />);
    expect(await screen.findByRole("tab", { name: /Menu Items/i })).toBeInTheDocument();
    expect(await screen.findByRole("tab", { name: /Modifier Library/i })).toBeInTheDocument();
  });

  it("offers a Sync from POS button", async () => {
    renderWithProviders(<Shell />);
    expect(
      await screen.findByRole("button", { name: /sync from pos/i })
    ).toBeInTheDocument();
  });

  it("offers an Add Item button", async () => {
    renderWithProviders(<Shell />);
    expect(
      await screen.findByRole("button", { name: /add item/i })
    ).toBeInTheDocument();
  });

  it("renders categorized menu items when the API returns data", async () => {
    server.use(
      http.get("*/api/restaurants/:id/menu", () =>
        HttpResponse.json([
          {
            id: "m1",
            name: "Margherita Pizza",
            description: "Tomato + basil",
            price_cents: 1500,
            category: "Pizza",
            available: true,
            allergens: [],
            modifiers: [],
          },
        ])
      )
    );
    renderWithProviders(<Shell />);

    await waitFor(() =>
      expect(screen.getByText(/Margherita Pizza/i)).toBeInTheDocument()
    );
  });

  it("survives a menu API failure", async () => {
    server.use(
      http.get("*/api/restaurants/:id/menu", () =>
        new HttpResponse(null, { status: 500 })
      )
    );
    renderWithProviders(<Shell />);

    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /Menu Items/i })).toBeInTheDocument()
    );
  });
});
