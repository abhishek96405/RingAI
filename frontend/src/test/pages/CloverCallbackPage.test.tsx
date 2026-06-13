import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";

// Mock only the two Clover network helpers so we can assert call counts and
// payloads. Everything else (api axios instance used by bootstrap, the
// sessionStorage/localStorage helpers) stays real via the actual spread.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    exchangeCloverCode: vi.fn(),
    getCloverConnectUrl: vi.fn(),
  };
});

import CloverCallbackPage from "@/pages/CloverCallbackPage";
import { exchangeCloverCode, getCloverConnectUrl } from "@/lib/api";

const CALLBACK = "/integrations/clover/callback";

function Shell() {
  return (
    <AppSessionProvider>
      <CloverCallbackPage />
    </AppSessionProvider>
  );
}

describe("CloverCallbackPage", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.mocked(exchangeCloverCode).mockReset();
    vi.mocked(getCloverConnectUrl).mockReset();
    vi.mocked(exchangeCloverCode).mockResolvedValue({
      data: { connected: true, restaurant_id: "tenant_a_restaurant" },
    } as never);
    vi.mocked(getCloverConnectUrl).mockResolvedValue({
      data: { connect_url: "https://sandbox.dev.clover.com/oauth/v2/authorize?client_id=x" },
    } as never);
  });

  it("exchanges code+merchant exactly once (survives StrictMode double-effect) and shows success", async () => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");

    renderWithProviders(
      <StrictMode>
        <Shell />
      </StrictMode>,
      { initialEntries: [`${CALLBACK}?code=auth_abc&merchant_id=M123`] }
    );

    await waitFor(() =>
      expect(screen.getByText(/Clover connected/i)).toBeInTheDocument()
    );

    expect(exchangeCloverCode).toHaveBeenCalledTimes(1);
    expect(exchangeCloverCode).toHaveBeenCalledWith({
      restaurant_id: "tenant_a_restaurant",
      code: "auth_abc",
      merchant_id: "M123",
    });
    // Merchant id surfaced in the success UI.
    expect(screen.getByText(/M123/)).toBeInTheDocument();
  });

  it("shows the error UI with a retry link when the exchange rejects (502)", async () => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");
    vi.mocked(exchangeCloverCode).mockRejectedValue({
      response: { status: 502, data: { detail: "Clover token exchange failed" } },
    } as never);

    renderWithProviders(<Shell />, {
      initialEntries: [`${CALLBACK}?code=bad_code&merchant_id=M123`],
    });

    await waitFor(() =>
      expect(screen.getByText(/Clover connection failed/i)).toBeInTheDocument()
    );
    expect(screen.getByText(/Clover token exchange failed/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /back to integrations/i });
    expect(link).toHaveAttribute("href", "/dashboard/integrations");
  });

  it("prompts sign-in and does NOT exchange when signed out", async () => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");

    renderWithProviders(<Shell />, {
      clerkUser: null,
      initialEntries: [`${CALLBACK}?code=auth_abc&merchant_id=M123`],
    });

    await waitFor(() =>
      expect(
        screen.getByText(/please sign in to finish connecting clover/i)
      ).toBeInTheDocument()
    );
    expect(exchangeCloverCode).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: /sign in/i })).toHaveAttribute("href", "/login");
  });

  it("initiates the authorize redirect on an App-Market launch (merchant_id, no code)", async () => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");

    renderWithProviders(<Shell />, {
      initialEntries: [`${CALLBACK}?merchant_id=M999`],
    });

    await waitFor(() =>
      expect(getCloverConnectUrl).toHaveBeenCalledWith("tenant_a_restaurant")
    );
    expect(exchangeCloverCode).not.toHaveBeenCalled();
    expect(screen.getByText(/redirecting to clover/i)).toBeInTheDocument();
  });

  it("prefers the pending sessionStorage id over the active localStorage id", async () => {
    localStorage.setItem("ringai.activeRestaurantId", "rest_local");
    sessionStorage.setItem("ringai.pendingCloverRestaurantId", "rest_pending");

    renderWithProviders(<Shell />, {
      initialEntries: [`${CALLBACK}?code=auth_abc&merchant_id=M123`],
    });

    await waitFor(() => expect(exchangeCloverCode).toHaveBeenCalledTimes(1));
    expect(exchangeCloverCode).toHaveBeenCalledWith({
      restaurant_id: "rest_pending",
      code: "auth_abc",
      merchant_id: "M123",
    });
  });
});
