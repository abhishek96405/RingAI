import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import LiveDemoSection from "@/components/landing/LiveDemoSection";

describe("Landing LiveDemoSection", () => {
  it("renders the demo intro pitch", () => {
    renderWithProviders(<LiveDemoSection />);
    expect(screen.getByRole("heading", { level: 2 })).toBeInTheDocument();
  });

  it("renders the bullet points highlighting Duuutah AI capabilities", () => {
    renderWithProviders(<LiveDemoSection />);
    expect(
      screen.getByText(/Natural, warm conversational voice/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Confirms details and sends text notifications/i)
    ).toBeInTheDocument();
  });

  it("starts in the idle 'Ready to Demo' state", () => {
    renderWithProviders(<LiveDemoSection />);
    expect(screen.getByText(/Ready to Demo/i)).toBeInTheDocument();
  });

  it("exposes a Start Demo button", () => {
    renderWithProviders(<LiveDemoSection />);
    expect(
      screen.getByRole("button", { name: /start demo|listen to demo/i })
    ).toBeInTheDocument();
  });
});
