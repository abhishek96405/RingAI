import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/utils/render";
import FAQSection from "@/components/landing/FAQSection";

describe("Landing FAQSection", () => {
  it("renders the FAQ heading", () => {
    renderWithProviders(<FAQSection />);
    // The section's heading varies; verify multiple FAQ questions are present
    expect(screen.getByText(/How does Duuutah AI handle phone orders\?/i)).toBeInTheDocument();
  });

  it("lists the canonical FAQ questions", () => {
    renderWithProviders(<FAQSection />);
    expect(screen.getByText(/How long does setup take\?/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Can Duuutah AI handle multiple calls at once\?/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Does it work with my existing phone number\?/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Is there a contract or can I cancel anytime\?/i)
    ).toBeInTheDocument();
  });

  it("expands an FAQ when the trigger is clicked", async () => {
    const user = userEvent.setup();
    renderWithProviders(<FAQSection />);
    const trigger = screen.getByRole("button", {
      name: /How does Duuutah AI handle phone orders\?/i,
    });
    await user.click(trigger);
    // Answer becomes visible after opening
    expect(
      await screen.findByText(/Orders are sent directly to your POS/i)
    ).toBeInTheDocument();
  });
});
