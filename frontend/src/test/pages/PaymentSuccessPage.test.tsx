import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import PaymentSuccessPage from "@/pages/PaymentSuccessPage";

describe("PaymentSuccessPage", () => {
  it("renders the success state by default", () => {
    renderWithProviders(<PaymentSuccessPage />, {
      initialEntries: ["/payment-success"],
    });
    expect(
      screen.getByRole("heading", { name: /Payment Received!/i })
    ).toBeInTheDocument();
    expect(screen.getByText(/being prepared/i)).toBeInTheDocument();
  });

  it("renders the cancelled state when ?cancelled=true", () => {
    renderWithProviders(<PaymentSuccessPage />, {
      initialEntries: ["/payment-success?cancelled=true"],
    });
    expect(
      screen.getByRole("heading", { name: /Payment Cancelled/i })
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Your order is still placed/i)
    ).toBeInTheDocument();
  });

  it("shows the Duuutah AI byline in either state", () => {
    renderWithProviders(<PaymentSuccessPage />, {
      initialEntries: ["/payment-success"],
    });
    expect(screen.getByText(/Powered by Duuutah AI/i)).toBeInTheDocument();
  });
});
