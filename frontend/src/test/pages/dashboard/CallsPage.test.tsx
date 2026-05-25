import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/utils/msw-server";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";
import CallsPage from "@/pages/dashboard/CallsPage";

function Shell() {
  return (
    <AppSessionProvider>
      <CallsPage />
    </AppSessionProvider>
  );
}

const SAMPLE_LIST = {
  calls: [
    {
      id: "call_1",
      caller_name: "Alice",
      caller_number: "+15555550100",
      status: "COMPLETED",
      duration_seconds: 90,
      quality_score: 92,
      order_total: 2500,
      started_at: "2026-05-20T10:00:00Z",
    },
    {
      id: "call_2",
      caller_name: "Bob",
      caller_number: "+15555550200",
      status: "ESCALATED",
      duration_seconds: 120,
      quality_score: 60,
      order_total: 0,
      started_at: "2026-05-20T11:00:00Z",
    },
  ],
  total: 2,
  pages: 1,
};

describe("CallsPage", () => {
  beforeEach(() => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");
  });

  it("renders the heading and total count", async () => {
    server.use(
      http.get("*/api/restaurants/:id/calls", () =>
        HttpResponse.json(SAMPLE_LIST)
      )
    );
    renderWithProviders(<Shell />);

    expect(await screen.findByRole("heading", { name: /call history/i })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/2 total calls/i)).toBeInTheDocument()
    );
  });

  it("renders call rows for each returned call", async () => {
    server.use(
      http.get("*/api/restaurants/:id/calls", () =>
        HttpResponse.json(SAMPLE_LIST)
      )
    );
    renderWithProviders(<Shell />);

    expect(await screen.findByText("Alice")).toBeInTheDocument();
    expect(await screen.findByText("Bob")).toBeInTheDocument();
  });

  it("shows the empty state when no calls are returned", async () => {
    server.use(
      http.get("*/api/restaurants/:id/calls", () =>
        HttpResponse.json({ calls: [], total: 0, pages: 1 })
      )
    );
    renderWithProviders(<Shell />);

    expect(await screen.findByText(/No calls found/i)).toBeInTheDocument();
  });

  it("opens the detail drawer when a call row is clicked", async () => {
    server.use(
      http.get("*/api/restaurants/:id/calls", () =>
        HttpResponse.json(SAMPLE_LIST)
      ),
      http.get("*/api/calls/call_1", () =>
        HttpResponse.json({
          id: "call_1",
          caller_name: "Alice Detailed",
          caller_number: "+15555550100",
          status: "COMPLETED",
          duration_seconds: 90,
          quality_score: 92,
          transcript: [
            { role: "ai", text: "Hi!", timestamp: "00:00" },
            { role: "customer", text: "I want a pizza", timestamp: "00:02" },
          ],
        })
      )
    );

    const user = userEvent.setup();
    renderWithProviders(<Shell />);

    const row = await screen.findByTestId("call-row-call_1");
    await user.click(row);

    expect(await screen.findByText("Alice Detailed")).toBeInTheDocument();
    expect(screen.getByText(/I want a pizza/i)).toBeInTheDocument();
  });

  it("filters by status through the dropdown", async () => {
    let observedStatus: string | null = null;
    server.use(
      http.get("*/api/restaurants/:id/calls", ({ request }) => {
        observedStatus = new URL(request.url).searchParams.get("status");
        return HttpResponse.json({ calls: [], total: 0, pages: 1 });
      })
    );

    const user = userEvent.setup();
    renderWithProviders(<Shell />);

    await waitFor(() => expect(screen.getByTestId("status-filter-select")).toBeInTheDocument());

    await user.click(screen.getByTestId("status-filter-select"));
    const completedOption = await screen.findByRole("option", { name: /completed/i });
    await user.click(completedOption);

    await waitFor(() => expect(observedStatus).toBe("COMPLETED"));
  });

  it("disables the CSV export button when total is 0", async () => {
    server.use(
      http.get("*/api/restaurants/:id/calls", () =>
        HttpResponse.json({ calls: [], total: 0, pages: 1 })
      )
    );
    renderWithProviders(<Shell />);

    const exportBtn = await screen.findByTestId("export-csv-btn");
    expect(exportBtn).toBeDisabled();
  });

  it("updates the search query and re-fetches", async () => {
    let observedSearch: string | null = null;
    server.use(
      http.get("*/api/restaurants/:id/calls", ({ request }) => {
        observedSearch = new URL(request.url).searchParams.get("search");
        return HttpResponse.json({ calls: [], total: 0, pages: 1 });
      })
    );

    const user = userEvent.setup();
    renderWithProviders(<Shell />);

    const searchInput = await screen.findByTestId("calls-search-input");
    await user.type(searchInput, "Alice");

    await waitFor(() => expect(observedSearch).toBe("Alice"));
  });
});
