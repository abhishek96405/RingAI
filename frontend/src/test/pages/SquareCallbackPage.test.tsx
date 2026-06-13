import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import SquareCallbackPage from "@/pages/SquareCallbackPage";

const CALLBACK = "/integrations/square/callback";

// The page is display-only: it reads status/merchant_id/reason from the query
// string the backend redirect set and renders success or error. No network, no
// auth, no side effects — so we render it directly inside the MemoryRouter.

describe("SquareCallbackPage", () => {
  it("shows the success state with the merchant id and a back link", () => {
    renderWithProviders(<SquareCallbackPage />, {
      initialEntries: [`${CALLBACK}?status=connected&merchant_id=ABC123`],
    });

    expect(screen.getByText(/Square connected/i)).toBeInTheDocument();
    expect(screen.getByText(/ABC123/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /back to integrations/i })
    ).toHaveAttribute("href", "/dashboard/integrations");
  });

  it("shows the error state with the exchange_failed message", () => {
    renderWithProviders(<SquareCallbackPage />, {
      initialEntries: [`${CALLBACK}?status=error&reason=exchange_failed`],
    });

    expect(screen.getByText(/Square connection failed/i)).toBeInTheDocument();
    expect(
      screen.getByText(/couldn't finish connecting your Square account/i)
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /back to integrations/i })
    ).toHaveAttribute("href", "/dashboard/integrations");
  });

  it("maps reason=invalid_state to the expired/invalid message", () => {
    renderWithProviders(<SquareCallbackPage />, {
      initialEntries: [`${CALLBACK}?status=error&reason=invalid_state`],
    });

    expect(screen.getByText(/Square connection failed/i)).toBeInTheDocument();
    expect(
      screen.getByText(/expired or is invalid/i)
    ).toBeInTheDocument();
  });
});
