import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/utils/msw-server";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider, useAppSession } from "@/context/AppSessionContext";

function SessionInspector() {
  const session = useAppSession();
  return (
    <div>
      <div data-testid="auth-loaded">{String(session.authLoaded)}</div>
      <div data-testid="bootstrapping">{String(session.bootstrapping)}</div>
      <div data-testid="signed-in">{String(session.isSignedIn ?? false)}</div>
      <div data-testid="active-restaurant-id">
        {session.activeRestaurant?.id ?? "none"}
      </div>
      <div data-testid="active-restaurant-name">
        {session.activeRestaurant?.name ?? "none"}
      </div>
      <div data-testid="onboarding-complete">
        {String(session.onboardingComplete)}
      </div>
      <div data-testid="restaurants-count">{session.restaurants.length}</div>
      <div data-testid="memberships-count">{session.memberships.length}</div>
      <button
        data-testid="set-other-restaurant"
        onClick={() =>
          session.setActiveRestaurant({
            id: "tenant_b_restaurant",
            name: "Tenant B",
            is_active: true,
          })
        }
      >
        Switch tenant
      </button>
      <button
        data-testid="refresh-session"
        onClick={() => session.refreshSession()}
      >
        Refresh
      </button>
    </div>
  );
}

describe("AppSessionContext (Duuutah AI session state)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("throws when useAppSession is called outside the provider", () => {
    expect(() =>
      renderWithProviders(<SessionInspector />, { clerkUser: null })
    ).toThrow(/useAppSession must be used inside AppSessionProvider/);
  });

  it("populates context from /api/me/bootstrap when signed in", async () => {
    renderWithProviders(
      <AppSessionProvider>
        <SessionInspector />
      </AppSessionProvider>
    );

    await waitFor(() =>
      expect(screen.getByTestId("active-restaurant-id").textContent).toBe(
        "tenant_a_restaurant"
      )
    );
    expect(screen.getByTestId("active-restaurant-name").textContent).toBe(
      "Test Restaurant A"
    );
    expect(screen.getByTestId("onboarding-complete").textContent).toBe("true");
    expect(screen.getByTestId("memberships-count").textContent).toBe("1");
    expect(screen.getByTestId("restaurants-count").textContent).toBe("1");
  });

  it("syncs active restaurant id to localStorage on bootstrap", async () => {
    renderWithProviders(
      <AppSessionProvider>
        <SessionInspector />
      </AppSessionProvider>
    );

    await waitFor(() =>
      expect(localStorage.getItem("ringai.activeRestaurantId")).toBe(
        "tenant_a_restaurant"
      )
    );
  });

  it("does not call bootstrap when the user is signed out", async () => {
    let called = false;
    server.use(
      http.get("*/api/me/bootstrap", () => {
        called = true;
        return HttpResponse.json({});
      })
    );

    renderWithProviders(
      <AppSessionProvider>
        <SessionInspector />
      </AppSessionProvider>,
      { clerkUser: null }
    );

    await waitFor(() =>
      expect(screen.getByTestId("bootstrapping").textContent).toBe("false")
    );

    expect(called).toBe(false);
    expect(screen.getByTestId("signed-in").textContent).toBe("false");
    expect(screen.getByTestId("active-restaurant-id").textContent).toBe("none");
  });

  it("recovers gracefully when bootstrap fails (does not crash)", async () => {
    server.use(
      http.get("*/api/me/bootstrap", () => new HttpResponse(null, { status: 500 }))
    );

    renderWithProviders(
      <AppSessionProvider>
        <SessionInspector />
      </AppSessionProvider>
    );

    await waitFor(() =>
      expect(screen.getByTestId("bootstrapping").textContent).toBe("false")
    );
    expect(screen.getByTestId("active-restaurant-id").textContent).toBe("none");
  });

  it("setActiveRestaurant updates context and localStorage", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <AppSessionProvider>
        <SessionInspector />
      </AppSessionProvider>
    );

    await waitFor(() =>
      expect(screen.getByTestId("active-restaurant-id").textContent).toBe(
        "tenant_a_restaurant"
      )
    );

    await user.click(screen.getByTestId("set-other-restaurant"));

    await waitFor(() =>
      expect(screen.getByTestId("active-restaurant-id").textContent).toBe(
        "tenant_b_restaurant"
      )
    );
    expect(localStorage.getItem("ringai.activeRestaurantId")).toBe(
      "tenant_b_restaurant"
    );
  });

  it("refreshSession re-fetches /api/me/bootstrap", async () => {
    let hits = 0;
    server.use(
      http.get("*/api/me/bootstrap", () => {
        hits += 1;
        return HttpResponse.json({
          active_restaurant: {
            id: "tenant_a_restaurant",
            name: `Refreshed #${hits}`,
            is_active: true,
          },
          memberships: [],
          restaurants: [
            { id: "tenant_a_restaurant", name: `Refreshed #${hits}`, is_active: true },
          ],
          onboarding_complete: true,
        });
      })
    );
    const user = userEvent.setup();
    renderWithProviders(
      <AppSessionProvider>
        <SessionInspector />
      </AppSessionProvider>
    );

    await waitFor(() =>
      expect(screen.getByTestId("active-restaurant-name").textContent).toBe(
        "Refreshed #1"
      )
    );

    await user.click(screen.getByTestId("refresh-session"));

    await waitFor(() =>
      expect(screen.getByTestId("active-restaurant-name").textContent).toBe(
        "Refreshed #2"
      )
    );
    expect(hits).toBeGreaterThanOrEqual(2);
  });

  it("falls back to the first restaurant when active_restaurant is missing", async () => {
    server.use(
      http.get("*/api/me/bootstrap", () =>
        HttpResponse.json({
          memberships: [],
          restaurants: [
            { id: "first_id", name: "First", is_active: true },
            { id: "second_id", name: "Second", is_active: false },
          ],
        })
      )
    );

    renderWithProviders(
      <AppSessionProvider>
        <SessionInspector />
      </AppSessionProvider>
    );

    await waitFor(() =>
      expect(screen.getByTestId("active-restaurant-id").textContent).toBe(
        "first_id"
      )
    );
  });

  it("derives onboarding_complete from restaurant.is_active when the field is absent", async () => {
    server.use(
      http.get("*/api/me/bootstrap", () =>
        HttpResponse.json({
          active_restaurant: { id: "r1", name: "R1", is_active: false },
          restaurants: [{ id: "r1", name: "R1", is_active: false }],
        })
      )
    );

    renderWithProviders(
      <AppSessionProvider>
        <SessionInspector />
      </AppSessionProvider>
    );

    await waitFor(() =>
      expect(screen.getByTestId("active-restaurant-id").textContent).toBe("r1")
    );
    expect(screen.getByTestId("onboarding-complete").textContent).toBe("false");
  });

  it("handles malformed memberships/restaurants without crashing", async () => {
    server.use(
      http.get("*/api/me/bootstrap", () =>
        HttpResponse.json({
          memberships: null,
          restaurants: undefined,
          active_restaurant: null,
        })
      )
    );

    renderWithProviders(
      <AppSessionProvider>
        <SessionInspector />
      </AppSessionProvider>
    );

    await waitFor(() =>
      expect(screen.getByTestId("bootstrapping").textContent).toBe("false")
    );
    expect(screen.getByTestId("memberships-count").textContent).toBe("0");
    expect(screen.getByTestId("restaurants-count").textContent).toBe("0");
  });
});
