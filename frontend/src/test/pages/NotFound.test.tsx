import { describe, it, expect, vi, afterEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import NotFound from "@/pages/NotFound";

describe("NotFound page", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("displays the 404 heading and recovery copy", () => {
    renderWithProviders(<NotFound />);
    expect(screen.getByRole("heading", { name: "404" })).toBeInTheDocument();
    expect(screen.getByText(/Oops! Page not found/i)).toBeInTheDocument();
  });

  it("offers a link back to the home page", () => {
    renderWithProviders(<NotFound />);
    const link = screen.getByRole("link", { name: /return to home/i });
    expect(link).toHaveAttribute("href", "/");
  });

  it("logs an error with the attempted pathname", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    renderWithProviders(<NotFound />, { initialEntries: ["/missing-page"] });
    expect(errorSpy).toHaveBeenCalled();
    const calledWith = errorSpy.mock.calls.flat().join(" ");
    expect(calledWith).toMatch(/404/);
    expect(calledWith).toMatch(/missing-page/);
  });
});
