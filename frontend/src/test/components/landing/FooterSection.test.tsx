import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import FooterSection from "@/components/landing/FooterSection";

describe("Landing FooterSection", () => {
  it("renders the Duuutah AI brand", () => {
    renderWithProviders(<FooterSection />);
    expect(screen.getAllByText(/Duuutah/i).length).toBeGreaterThan(0);
  });

  it("lists Product, Company, and Legal columns", () => {
    renderWithProviders(<FooterSection />);
    expect(screen.getByText("Product")).toBeInTheDocument();
    expect(screen.getByText("Company")).toBeInTheDocument();
    expect(screen.getByText("Legal")).toBeInTheDocument();
  });

  it("renders individual links inside each column", () => {
    renderWithProviders(<FooterSection />);
    expect(screen.getByText("Features")).toBeInTheDocument();
    expect(screen.getByText("Pricing")).toBeInTheDocument();
    expect(screen.getByText("Privacy")).toBeInTheDocument();
    expect(screen.getByText("Terms")).toBeInTheDocument();
  });
});
