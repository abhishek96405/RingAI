import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import PricingSection from "@/components/landing/PricingSection";

describe("Landing PricingSection", () => {
  it("renders Starter and Pro plans with prices", () => {
    renderWithProviders(<PricingSection />);
    expect(screen.getByText("Starter")).toBeInTheDocument();
    expect(screen.getByText("Pro")).toBeInTheDocument();
    expect(screen.getByText("$199")).toBeInTheDocument();
    expect(screen.getByText("$349")).toBeInTheDocument();
  });

  it("shows the Starter plan call volume", () => {
    renderWithProviders(<PricingSection />);
    expect(screen.getByText(/500 AI calls\/month/i)).toBeInTheDocument();
  });

  it("shows the Pro plan call volume and exclusive features", () => {
    renderWithProviders(<PricingSection />);
    expect(screen.getByText(/1,000 AI calls\/month/i)).toBeInTheDocument();
    expect(screen.getByText(/AI delivery order handling/i)).toBeInTheDocument();
    expect(screen.getByText(/AI table reservations/i)).toBeInTheDocument();
  });

  it("provides CTAs linking to /signup", () => {
    renderWithProviders(<PricingSection />);
    const ctas = screen.getAllByRole("link");
    expect(ctas.some((c) => c.getAttribute("href")?.includes("/signup"))).toBe(true);
  });
});
