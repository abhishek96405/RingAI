import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import Index from "@/pages/Index";

describe("Index landing page", () => {
  it("renders the marketing landing page composed of all sections", () => {
    renderWithProviders(<Index />);
    // Hero — single h1, now "Never miss a call."
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/never miss/i);
    // Pricing — scope to the plan headings (the cost calculator also renders "Starter"/"Pro" labels)
    expect(screen.getByRole("heading", { name: "Starter" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Pro" })).toBeInTheDocument();
    // FAQ — assert current copy
    expect(screen.getByText(/which pos systems do you support\?/i)).toBeInTheDocument();
    // Final CTA — match the full heading so it doesn't collide with the hero h1
    expect(screen.getByRole("heading", { name: /ready to never miss/i })).toBeInTheDocument();
  });
});
