import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import CTASection from "@/components/landing/CTASection";

describe("Landing CTASection", () => {
  it("renders the closing call-to-action heading", () => {
    renderWithProviders(<CTASection />);
    expect(
      screen.getByRole("heading", { name: /never miss/i })
    ).toBeInTheDocument();
  });

  it("links to /signup", () => {
    renderWithProviders(<CTASection />);
    const links = screen.getAllByRole("link");
    expect(links.some((l) => l.getAttribute("href")?.startsWith("/signup"))).toBe(
      true
    );
  });
});
