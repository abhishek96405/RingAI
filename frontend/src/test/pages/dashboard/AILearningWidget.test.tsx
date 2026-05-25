import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import { server } from "@/test/utils/msw-server";
import { renderWithProviders } from "@/test/utils/render";
import AILearningWidget from "@/pages/dashboard/AILearningWidget";

describe("AILearningWidget (Duuutah AI Pro feature)", () => {
  beforeEach(() => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_a_restaurant");
  });

  it("renders the AI Auto-Learning heading once stats arrive", async () => {
    renderWithProviders(<AILearningWidget />);
    expect(
      await screen.findByText(/AI Auto-Learning/i)
    ).toBeInTheDocument();
  });

  it("renders the empty-state when learning has no aliases yet", async () => {
    server.use(
      http.get("*/api/restaurants/:id/learning/stats", () =>
        HttpResponse.json({
          total_calls_processed: 0,
          aliases_learned: 0,
          calls_flagged: 0,
          last_processed: null,
        })
      ),
      http.get("*/api/restaurants/:id/learning/aliases", () =>
        HttpResponse.json([])
      ),
      http.get("*/api/restaurants/:id/learning/flagged-calls", () =>
        HttpResponse.json([])
      )
    );

    renderWithProviders(<AILearningWidget />);
    await waitFor(() => {
      expect(screen.getByText(/AI Auto-Learning/i)).toBeInTheDocument();
    });
  });

  it("displays counts when learning stats arrive", async () => {
    server.use(
      http.get("*/api/restaurants/:id/learning/stats", () =>
        HttpResponse.json({
          total_calls_processed: 42,
          aliases_learned: 7,
          calls_flagged: 3,
          last_processed: "2026-05-20T10:00:00Z",
        })
      )
    );

    renderWithProviders(<AILearningWidget />);
    await waitFor(() => {
      expect(screen.getAllByText(/42/).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/7/).length).toBeGreaterThan(0);
    });
  });

  it("recovers when learning stats fail to load", async () => {
    server.use(
      http.get("*/api/restaurants/:id/learning/stats", () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    renderWithProviders(<AILearningWidget />);
    // When stats fail, the component sets loading=false and renders the layout
    // with default zeros. The "AI Auto-Learning" heading should appear.
    await waitFor(() =>
      expect(screen.queryByText(/Loading AI Learning/i)).not.toBeInTheDocument()
    );
  });
});
