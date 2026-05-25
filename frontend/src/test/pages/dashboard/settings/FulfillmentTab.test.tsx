import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/utils/render";
import FulfillmentTab from "@/pages/dashboard/settings/FulfillmentTab";

const makeProps = (overrides: Partial<Parameters<typeof FulfillmentTab>[0]> = {}) => ({
  restaurant: {
    pickup_enabled: true,
    delivery_enabled: false,
    reservations_enabled: false,
    plan: "STARTER",
    avg_prep_time_minutes: 20,
  },
  setRestaurant: vi.fn(),
  config: {},
  setConfig: vi.fn(),
  saving: false,
  onSaveRestaurant: vi.fn().mockResolvedValue(undefined),
  onSaveConfig: vi.fn().mockResolvedValue(undefined),
  ...overrides,
});

describe("FulfillmentTab", () => {
  it("renders the Fulfillment heading", () => {
    renderWithProviders(<FulfillmentTab {...makeProps()} />);
    expect(
      screen.getByRole("heading", { name: /^Fulfillment$/i })
    ).toBeInTheDocument();
  });

  it("shows Pickup, Delivery, and Reservations toggles", () => {
    renderWithProviders(<FulfillmentTab {...makeProps()} />);
    expect(screen.getByText("Pickup Enabled")).toBeInTheDocument();
    expect(screen.getByText("Delivery Enabled")).toBeInTheDocument();
    expect(screen.getByText("Reservations Enabled")).toBeInTheDocument();
  });

  it("marks delivery and reservations as Pro-gated on the STARTER plan", () => {
    renderWithProviders(<FulfillmentTab {...makeProps()} />);
    expect(screen.getAllByText(/\(Pro\)/i).length).toBeGreaterThanOrEqual(2);
  });

  it("does not mark them as Pro-gated on the PRO plan", () => {
    renderWithProviders(
      <FulfillmentTab
        {...makeProps({
          restaurant: { ...makeProps().restaurant, plan: "PRO" },
        })}
      />
    );
    expect(screen.queryAllByText(/\(Pro\)/i)).toHaveLength(0);
  });

  it("renders Delivery Settings only when delivery_enabled is true", () => {
    const { rerender } = renderWithProviders(<FulfillmentTab {...makeProps()} />);
    expect(screen.queryByText(/Delivery Settings/i)).not.toBeInTheDocument();

    rerender(
      <FulfillmentTab
        {...makeProps({
          restaurant: { ...makeProps().restaurant, delivery_enabled: true, plan: "PRO" },
        })}
      />
    );
    expect(screen.getByText(/Delivery Settings/i)).toBeInTheDocument();
  });

  it("invokes both save handlers when the Save button is clicked", async () => {
    const user = userEvent.setup();
    const onSaveRestaurant = vi.fn().mockResolvedValue(undefined);
    const onSaveConfig = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(
      <FulfillmentTab
        {...makeProps({ onSaveRestaurant, onSaveConfig })}
      />
    );

    await user.click(screen.getByRole("button", { name: /save fulfillment/i }));
    expect(onSaveRestaurant).toHaveBeenCalled();
    expect(onSaveConfig).toHaveBeenCalled();
  });
});
