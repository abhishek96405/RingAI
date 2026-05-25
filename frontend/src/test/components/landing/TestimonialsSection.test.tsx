import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import TestimonialsSection from "@/components/landing/TestimonialsSection";

describe("Landing TestimonialsSection", () => {
  it("renders multiple testimonial quotes", () => {
    renderWithProviders(<TestimonialsSection />);
    expect(screen.getByText(/Maria Chen/i)).toBeInTheDocument();
    expect(screen.getByText(/Dr\. James Wilson/i)).toBeInTheDocument();
    expect(screen.getByText(/Sarah Kim/i)).toBeInTheDocument();
  });

  it("includes the Duuutah AI customer impact quote", () => {
    renderWithProviders(<TestimonialsSection />);
    expect(screen.getByText(/Duuutah AI cut our missed calls by 90%/i)).toBeInTheDocument();
  });
});
