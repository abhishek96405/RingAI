import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/utils/render";
import HeroSection from "@/components/landing/HeroSection";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe("Landing HeroSection", () => {
  it("renders the Duuutah AI tagline headline", () => {
    renderWithProviders(<HeroSection />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /AI Receptionist/i
    );
  });

  it("offers all five business-type selection buttons", () => {
    renderWithProviders(<HeroSection />);
    expect(screen.getByRole("button", { name: /restaurants/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /clinics/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /salons/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /home services/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /legal/i })).toBeInTheDocument();
  });

  it("navigates to /signup with business_type query when a business is chosen", async () => {
    mockNavigate.mockClear();
    const user = userEvent.setup();
    renderWithProviders(<HeroSection />);

    await user.click(screen.getByRole("button", { name: /clinics/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/signup?business_type=clinic");
  });

  it("renders the primary CTA linking to /signup", () => {
    renderWithProviders(<HeroSection />);
    const cta = screen.getByTestId("hero-get-started-btn");
    expect(cta.closest("a")).toHaveAttribute("href", "/signup");
  });

  it("displays the 5,000+ businesses social proof", () => {
    renderWithProviders(<HeroSection />);
    expect(screen.getByText(/5,000\+ businesses/i)).toBeInTheDocument();
    expect(screen.getByText(/4\.9\/5/)).toBeInTheDocument();
  });
});
