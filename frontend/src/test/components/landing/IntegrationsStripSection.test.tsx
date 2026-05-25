import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import IntegrationsStripSection from "@/components/landing/IntegrationsStripSection";

describe("Landing IntegrationsStripSection", () => {
  it("renders all listed integration partners", () => {
    renderWithProviders(<IntegrationsStripSection />);
    expect(screen.getByText("OpenTable")).toBeInTheDocument();
    expect(screen.getByText("Resy")).toBeInTheDocument();
    expect(screen.getByText("Toast POS")).toBeInTheDocument();
    expect(screen.getByText("Yelp")).toBeInTheDocument();
    expect(screen.getByText("SevenRooms")).toBeInTheDocument();
    expect(screen.getByText("Square")).toBeInTheDocument();
  });

  it("includes a short description for each integration", () => {
    renderWithProviders(<IntegrationsStripSection />);
    expect(screen.getByText(/Automated reservation management/i)).toBeInTheDocument();
    expect(screen.getByText(/Order & menu integration/i)).toBeInTheDocument();
    expect(screen.getByText(/Payment & POS integration/i)).toBeInTheDocument();
  });
});
