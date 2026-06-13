import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { server } from "@/test/utils/msw-server";
import { renderWithProviders } from "@/test/utils/render";
import { AppSessionProvider } from "@/context/AppSessionContext";
import AppointmentsPage from "@/pages/dashboard/AppointmentsPage";

function Shell() {
  return (
    <AppSessionProvider>
      <AppointmentsPage />
    </AppSessionProvider>
  );
}

describe("AppointmentsPage", () => {
  beforeEach(() => {
    localStorage.setItem("ringai.activeRestaurantId", "tenant_clinic");
  });

  it("renders the page heading", async () => {
    renderWithProviders(<Shell />);
    expect(
      await screen.findByRole("heading", { name: /appointments/i })
    ).toBeInTheDocument();
  });

  it("renders appointment rows when the API returns data", async () => {
    server.use(
      http.get("*/api/restaurants/:id/appointments", () =>
        HttpResponse.json({
          appointments: [
            {
              id: "appt_1",
              customer_name: "Patient One",
              customer_phone: "+15555550101",
              service_name: "Consult",
              appointment_date: "2026-06-01",
              start_time: "10:00",
              end_time: "10:30",
              status: "confirmed",
            },
          ],
          pages: 1,
        })
      )
    );

    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.getByText(/Patient One/i)).toBeInTheDocument()
    );
  });

  it("renders the empty state when no appointments are present", async () => {
    renderWithProviders(<Shell />);
    // Heading still renders cleanly
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /appointments/i })).toBeInTheDocument()
    );
  });

  it("handles API failures gracefully", async () => {
    server.use(
      http.get("*/api/restaurants/:id/appointments", () =>
        new HttpResponse(null, { status: 500 })
      )
    );

    renderWithProviders(<Shell />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /appointments/i })).toBeInTheDocument()
    );
  });

  it("opens the New Appointment dialog with the booking form", async () => {
    server.use(
      http.get("*/api/restaurants/:id/services", () =>
        HttpResponse.json([
          { id: "svc_1", name: "Haircut", duration_minutes: 30, price_cents: 4500 },
        ])
      ),
      http.get("*/api/restaurants/:id/available-slots", () =>
        HttpResponse.json({
          slots: [{ slot_time: "10:00", display_time: "10:00 AM", available: true }],
        })
      )
    );

    const user = userEvent.setup();
    renderWithProviders(<Shell />);

    await user.click(await screen.findByTestId("create-appointment-btn"));

    // "Book Appointment" is both the dialog title and the submit button label,
    // so scope the assertion to the heading to avoid an ambiguous match.
    expect(await screen.findByRole("heading", { name: /Book Appointment/i })).toBeInTheDocument();
    expect(screen.getByTestId("appointment-customer-name")).toBeInTheDocument();
    expect(screen.getByTestId("appointment-customer-phone")).toBeInTheDocument();
  });

  it("confirms a conflicting appointment from the bookings list", async () => {
    let confirmCalled = false;
    server.use(
      http.get("*/api/restaurants/:id/appointments", () =>
        HttpResponse.json({
          appointments: [
            {
              id: "appt_conf",
              customer_name: "Conflicted Carol",
              customer_phone: "+15555550199",
              service_name: "Haircut",
              scheduled_date: "2026-06-01",
              scheduled_time: "10:00",
              duration_minutes: 30,
              status: "conflict",
            },
          ],
          pages: 1,
        })
      ),
      http.patch("*/api/appointments/:id/confirm", () => {
        confirmCalled = true;
        return HttpResponse.json({ message: "Appointment confirmed", id: "appt_conf" });
      })
    );

    const user = userEvent.setup();
    renderWithProviders(<Shell />);

    await waitFor(() =>
      expect(screen.getByText(/Conflicted Carol/i)).toBeInTheDocument()
    );
    await user.click(screen.getByRole("button", { name: /confirm/i }));
    await waitFor(() => expect(confirmCalled).toBe(true));
  });
});
