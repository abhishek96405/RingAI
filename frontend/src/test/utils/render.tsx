import { type ReactElement, type ReactNode } from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, type MemoryRouterProps } from "react-router-dom";
import { MockClerkProvider, type MockClerkUser } from "./mock-clerk";

interface CustomRenderOptions extends Omit<RenderOptions, "wrapper"> {
  initialEntries?: MemoryRouterProps["initialEntries"];
  clerkUser?: MockClerkUser | null;
  clerkLoaded?: boolean;
  queryClient?: QueryClient;
  withRouter?: boolean;
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

const DEFAULT_USER: MockClerkUser = {
  id: "user_test",
  emailAddress: "test@duuutah.ai",
  emailAddresses: [{ emailAddress: "test@duuutah.ai" }],
  firstName: "Test",
  lastName: "User",
  fullName: "Test User",
};

export function renderWithProviders(
  ui: ReactElement,
  options: CustomRenderOptions = {}
) {
  const {
    initialEntries = ["/"],
    clerkUser = DEFAULT_USER,
    clerkLoaded = true,
    queryClient,
    withRouter = true,
    ...rtlOptions
  } = options;

  const qc = queryClient ?? makeQueryClient();

  function Wrapper({ children }: { children: ReactNode }) {
    const body = (
      <MockClerkProvider user={clerkUser} isLoaded={clerkLoaded}>
        {children}
      </MockClerkProvider>
    );
    return (
      <QueryClientProvider client={qc}>
        {withRouter ? (
          <MemoryRouter initialEntries={initialEntries}>{body}</MemoryRouter>
        ) : (
          body
        )}
      </QueryClientProvider>
    );
  }

  const result = render(ui, { wrapper: Wrapper, ...rtlOptions });
  return { ...result, queryClient: qc };
}

export { DEFAULT_USER };
