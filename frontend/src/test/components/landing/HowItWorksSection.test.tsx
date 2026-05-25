import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import HowItWorksSection from "@/components/landing/HowItWorksSection";

describe("Landing HowItWorksSection", () => {
  it("renders the section heading", () => {
    renderWithProviders(<HowItWorksSection />);
    expect(
      screen.getByRole("heading", { name: /live in under 10 minutes/i })
    ).toBeInTheDocument();
  });

  it("lists all four onboarding steps with their numbers", () => {
    renderWithProviders(<HowItWorksSection />);
    expect(screen.getByText(/Step 01/i)).toBeInTheDocument();
    expect(screen.getByText(/Step 02/i)).toBeInTheDocument();
    expect(screen.getByText(/Step 03/i)).toBeInTheDocument();
    expect(screen.getByText(/Step 04/i)).toBeInTheDocument();
    expect(screen.getByText(/Sign Up & Choose Business/i)).toBeInTheDocument();
    expect(screen.getByText(/Configure Your AI/i)).toBeInTheDocument();
    expect(screen.getByText(/Connect Your Phone/i)).toBeInTheDocument();
    expect(screen.getByText(/Monitor & Grow/i)).toBeInTheDocument();
  });
});
