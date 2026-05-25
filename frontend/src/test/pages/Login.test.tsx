import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import Login from "@/pages/Login";

describe("Login page", () => {
  it("renders the Duuutah AI brand link back to the landing page", () => {
    renderWithProviders(<Login />);
    const brandLinks = screen.getAllByRole("link", { name: /duuutah ai/i });
    expect(brandLinks.length).toBeGreaterThan(0);
    expect(brandLinks[0]).toHaveAttribute("href", "/");
  });

  it("shows the welcome heading and Duuutah AI dashboard sub-copy", () => {
    renderWithProviders(<Login />);
    expect(screen.getByRole("heading", { name: /welcome back/i })).toBeInTheDocument();
    expect(
      screen.getByText(/Sign in to your Duuutah AI dashboard/i)
    ).toBeInTheDocument();
  });

  it("renders the Clerk sign-in form via the SignIn component", () => {
    renderWithProviders(<Login />);
    expect(screen.getByTestId("clerk-signin")).toBeInTheDocument();
  });

  it("renders the marketing panel content on wider viewports", () => {
    renderWithProviders(<Login />);
    expect(
      screen.getByRole("heading", { name: /Your AI Receptionist Awaits/i })
    ).toBeInTheDocument();
  });
});
