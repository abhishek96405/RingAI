import { createContext, useContext, type ReactNode } from "react";
import { vi } from "vitest";

export interface MockClerkUser {
  id: string;
  emailAddress?: string;
  emailAddresses?: { emailAddress: string }[];
  firstName?: string;
  lastName?: string;
  fullName?: string;
}

interface MockClerkContextValue {
  user: MockClerkUser | null;
  isLoaded: boolean;
  isSignedIn: boolean;
}

const MockClerkContext = createContext<MockClerkContextValue>({
  user: null,
  isLoaded: true,
  isSignedIn: false,
});

export function MockClerkProvider({
  user,
  isLoaded = true,
  children,
}: {
  user: MockClerkUser | null;
  isLoaded?: boolean;
  children: ReactNode;
}) {
  const value: MockClerkContextValue = {
    user,
    isLoaded,
    isSignedIn: user !== null,
  };
  return (
    <MockClerkContext.Provider value={value}>{children}</MockClerkContext.Provider>
  );
}

export function useMockClerk() {
  return useContext(MockClerkContext);
}

// Stable getToken/signOut references so that consumers using them in effect
// deps (e.g. AppSessionContext) don't re-render infinitely.
const stableGetToken = vi.fn(async () => "mock-clerk-jwt");
const stableGetTokenSignedOut = vi.fn(async () => null);
const stableSignOut = vi.fn();

vi.mock("@clerk/clerk-react", async () => {
  const React = await import("react");
  const reactDom = await import("react-router-dom");

  function useClerkCtx() {
    return React.useContext(MockClerkContext);
  }

  return {
    useUser: () => {
      const ctx = useClerkCtx();
      return React.useMemo(
        () => ({
          user: ctx.user,
          isLoaded: ctx.isLoaded,
          isSignedIn: ctx.isSignedIn,
        }),
        [ctx.user, ctx.isLoaded, ctx.isSignedIn]
      );
    },
    useAuth: () => {
      const ctx = useClerkCtx();
      return React.useMemo(
        () => ({
          isLoaded: ctx.isLoaded,
          isSignedIn: ctx.isSignedIn,
          userId: ctx.user?.id ?? null,
          sessionId: ctx.user ? "mock_session" : null,
          getToken: ctx.user ? stableGetToken : stableGetTokenSignedOut,
          signOut: stableSignOut,
        }),
        [ctx.user, ctx.isLoaded, ctx.isSignedIn]
      );
    },
    SignedIn: ({ children }: { children: ReactNode }) => {
      const ctx = useClerkCtx();
      return ctx.user !== null ? React.createElement(React.Fragment, null, children) : null;
    },
    SignedOut: ({ children }: { children: ReactNode }) => {
      const ctx = useClerkCtx();
      return ctx.user === null ? React.createElement(React.Fragment, null, children) : null;
    },
    ClerkLoaded: ({ children }: { children: ReactNode }) => {
      const ctx = useClerkCtx();
      return ctx.isLoaded ? React.createElement(React.Fragment, null, children) : null;
    },
    ClerkLoading: ({ children }: { children: ReactNode }) => {
      const ctx = useClerkCtx();
      return !ctx.isLoaded ? React.createElement(React.Fragment, null, children) : null;
    },
    ClerkProvider: ({ children }: { children: ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    SignIn: () => React.createElement("div", { "data-testid": "clerk-signin" }, "Clerk Sign In"),
    SignUp: () => React.createElement("div", { "data-testid": "clerk-signup" }, "Clerk Sign Up"),
    SignInButton: ({ children }: { children?: ReactNode }) =>
      React.createElement("button", { "data-testid": "clerk-signin-btn" }, children ?? "Sign In"),
    SignOutButton: ({ children, redirectUrl }: { children?: ReactNode; redirectUrl?: string }) => {
      // Render as a passthrough so consumers can wrap their own button
      // and clicks navigate to the redirectUrl
      void redirectUrl;
      return React.createElement(React.Fragment, null, children ?? "Sign Out");
    },
    UserButton: () =>
      React.createElement("button", { "data-testid": "clerk-userbutton" }, "User"),
    RedirectToSignIn: () => {
      // Use react-router's Navigate to simulate Clerk's redirect
      return React.createElement(reactDom.Navigate, { to: "/login", replace: true });
    },
  };
});
