import { describe, it, expect } from "vitest";
import { Route, Routes } from "react-router-dom";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/utils/render";
import ProtectedRoute from "@/components/ProtectedRoute";
import { AppSessionProvider } from "@/context/AppSessionContext";

function PublicLoginPage() {
  return <div data-testid="login-page">Sign in to Duuutah AI</div>;
}

function PrivateContent() {
  return <div data-testid="private-content">Secret dashboard</div>;
}

function AppShell() {
  return (
    <AppSessionProvider>
      <Routes>
        <Route path="/login" element={<PublicLoginPage />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <PrivateContent />
            </ProtectedRoute>
          }
        />
      </Routes>
    </AppSessionProvider>
  );
}

describe("ProtectedRoute", () => {
  it("renders the loading state while Clerk is loading", () => {
    renderWithProviders(<AppShell />, {
      initialEntries: ["/dashboard"],
      clerkLoaded: false,
    });
    expect(screen.getByText(/Loading your workspace/i)).toBeInTheDocument();
  });

  it("redirects to /login when the user is signed out", async () => {
    renderWithProviders(<AppShell />, {
      initialEntries: ["/dashboard"],
      clerkUser: null,
    });

    await waitFor(() =>
      expect(screen.getByTestId("login-page")).toBeInTheDocument()
    );
    expect(screen.queryByTestId("private-content")).not.toBeInTheDocument();
  });

  it("renders protected children when the user is signed in and bootstrap completed", async () => {
    renderWithProviders(<AppShell />, {
      initialEntries: ["/dashboard"],
      clerkUser: { id: "user_test" },
    });

    await waitFor(() =>
      expect(screen.getByTestId("private-content")).toBeInTheDocument()
    );
  });
});
