import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { renderWithProviders } from "@/test/utils/render";
import { NavLink } from "@/components/NavLink";

describe("NavLink (forwardRef wrapper)", () => {
  it("renders an anchor pointing at the provided 'to'", () => {
    renderWithProviders(
      <NavLink to="/dashboard" className="base">
        Dashboard
      </NavLink>
    );

    const link = screen.getByRole("link", { name: /dashboard/i });
    expect(link).toHaveAttribute("href", "/dashboard");
  });

  it("applies the base className", () => {
    renderWithProviders(
      <NavLink to="/dashboard" className="base">
        Dashboard
      </NavLink>
    );
    expect(screen.getByRole("link")).toHaveClass("base");
  });

  it("merges activeClassName when the route matches", () => {
    renderWithProviders(
      <Routes>
        <Route
          path="/dashboard"
          element={
            <NavLink
              to="/dashboard"
              className="base"
              activeClassName="is-active"
            >
              Dashboard
            </NavLink>
          }
        />
      </Routes>,
      { initialEntries: ["/dashboard"] }
    );

    const link = screen.getByRole("link", { name: /dashboard/i });
    expect(link).toHaveClass("base");
    expect(link).toHaveClass("is-active");
  });

  it("does not apply activeClassName for non-matching routes", () => {
    renderWithProviders(
      <Routes>
        <Route
          path="/settings"
          element={
            <NavLink
              to="/dashboard"
              className="base"
              activeClassName="is-active"
            >
              Dashboard
            </NavLink>
          }
        />
      </Routes>,
      { initialEntries: ["/settings"] }
    );

    const link = screen.getByRole("link");
    expect(link).not.toHaveClass("is-active");
  });

  it("forwards ref to the underlying anchor", () => {
    let captured: HTMLAnchorElement | null = null;
    renderWithProviders(
      <NavLink
        to="/foo"
        ref={(el: HTMLAnchorElement | null) => {
          captured = el;
        }}
      >
        Foo
      </NavLink>
    );
    expect(captured).not.toBeNull();
    expect((captured as unknown as HTMLAnchorElement | null)?.tagName).toBe("A");
  });
});
