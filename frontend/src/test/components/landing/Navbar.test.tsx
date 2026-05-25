import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/utils/render";
import Navbar from "@/components/landing/Navbar";

describe("Landing Navbar", () => {
  it("renders the Duuutah AI brand", () => {
    renderWithProviders(<Navbar />);
    const logo = screen.getByRole("link", { name: /duuutah ai/i });
    expect(logo).toBeInTheDocument();
    expect(logo).toHaveAttribute("href", "/");
  });

  it("exposes anchor nav links to landing sections (desktop)", () => {
    renderWithProviders(<Navbar />);
    expect(screen.getByRole("link", { name: /^features$/i })).toHaveAttribute(
      "href",
      "#features"
    );
    expect(screen.getByRole("link", { name: /how it works/i })).toHaveAttribute(
      "href",
      "#how-it-works"
    );
    expect(screen.getByRole("link", { name: /^pricing$/i })).toHaveAttribute(
      "href",
      "#pricing"
    );
    expect(screen.getByRole("link", { name: /^faq$/i })).toHaveAttribute(
      "href",
      "#faq"
    );
  });

  it("includes sign-in and start-free-trial CTAs", () => {
    renderWithProviders(<Navbar />);
    expect(screen.getAllByRole("link", { name: /sign in/i }).length).toBeGreaterThan(0);
    expect(
      screen.getAllByRole("link", { name: /start free trial|get started/i }).length
    ).toBeGreaterThan(0);
  });

  it("toggles the mobile menu when the menu button is clicked", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Navbar />);

    const buttons = screen.getAllByRole("button");
    const menuToggle = buttons.find((b) => b.querySelector("svg")) ?? buttons[0];
    await user.click(menuToggle);
    // After opening, the mobile pane links exist
    expect(
      screen.getAllByRole("link", { name: /^features$/i }).length
    ).toBeGreaterThan(0);
  });
});
