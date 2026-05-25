import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import Signup from "@/pages/Signup";

describe("Signup page", () => {
  it("renders the Duuutah AI signup heading", () => {
    renderWithProviders(<Signup />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
  });

  it("renders the Clerk SignUp component", () => {
    renderWithProviders(<Signup />);
    expect(screen.getByTestId("clerk-signup")).toBeInTheDocument();
  });

  it("shows the restaurant business type context when query param is set", () => {
    renderWithProviders(<Signup />, {
      initialEntries: ["/signup?business_type=restaurant"],
    });
    expect(
      screen.getByText(/Restaurant \/ Food Service/i)
    ).toBeInTheDocument();
  });

  it("shows the clinic business type context when query param is set", () => {
    renderWithProviders(<Signup />, {
      initialEntries: ["/signup?business_type=clinic"],
    });
    expect(screen.getByText(/Clinic \/ Healthcare/i)).toBeInTheDocument();
  });

  it("persists the selected business_type to localStorage when the query param is set", () => {
    renderWithProviders(<Signup />, {
      initialEntries: ["/signup?business_type=salon"],
    });
    expect(localStorage.getItem("ringai_selected_business_type")).toBe("salon");
  });
});
