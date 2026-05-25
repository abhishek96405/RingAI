import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import FeaturesSection from "@/components/landing/FeaturesSection";

describe("Landing FeaturesSection", () => {
  it("renders the section heading", () => {
    renderWithProviders(<FeaturesSection />);
    expect(
      screen.getByRole("heading", { name: /everything your business phone needs/i })
    ).toBeInTheDocument();
  });

  it("lists the major Duuutah AI feature cards", () => {
    renderWithProviders(<FeaturesSection />);
    expect(screen.getByText(/AI Phone Agent/i)).toBeInTheDocument();
    expect(screen.getByText(/Smart Understanding/i)).toBeInTheDocument();
    expect(screen.getByText(/Multilingual Support/i)).toBeInTheDocument();
    expect(screen.getByText(/Smart Scheduling/i)).toBeInTheDocument();
    expect(screen.getByText(/Real-Time Analytics/i)).toBeInTheDocument();
    expect(screen.getByText(/24\/7 Availability/i)).toBeInTheDocument();
    expect(screen.getByText(/Enterprise Security/i)).toBeInTheDocument();
  });

  it("calls out vertical examples for clinics, salons, and home services", () => {
    renderWithProviders(<FeaturesSection />);
    expect(screen.getByText(/Clinics/i)).toBeInTheDocument();
    expect(screen.getByText(/Salons/i)).toBeInTheDocument();
    expect(screen.getByText(/Home Services/i)).toBeInTheDocument();
  });
});
