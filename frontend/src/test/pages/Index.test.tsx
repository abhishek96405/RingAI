import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import Index from "@/pages/Index";

describe("Index landing page", () => {
  it("renders the marketing landing page composed of all sections", () => {
    renderWithProviders(<Index />);
    // Hero
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /AI Receptionist/i
    );
    // Pricing
    expect(screen.getByText("Starter")).toBeInTheDocument();
    expect(screen.getByText("Pro")).toBeInTheDocument();
    // FAQ
    expect(
      screen.getByText(/How does Duuutah AI handle phone orders\?/i)
    ).toBeInTheDocument();
    // CTA
    expect(
      screen.getByRole("heading", { name: /never miss/i })
    ).toBeInTheDocument();
  });
});
