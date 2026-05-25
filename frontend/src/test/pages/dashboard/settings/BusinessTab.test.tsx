import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/utils/render";
import BusinessTab from "@/pages/dashboard/settings/BusinessTab";

const makeProps = (overrides: Partial<Parameters<typeof BusinessTab>[0]> = {}) => ({
  restaurant: {
    name: "Test Restaurant",
    cuisine_type: "italian",
    owner_name: "Owner",
    owner_email: "o@example.com",
    business_phone: "+15555550101",
    billing_email: "b@example.com",
    _street: "123 Main",
    _city: "Townsville",
    _state: "CA",
    _zip: "12345",
  },
  setRestaurant: vi.fn(),
  config: { escalation_phone_number: "+15555550199" },
  setConfig: vi.fn(),
  businessType: "restaurant",
  isAppointmentBusiness: false,
  saving: false,
  errors: {},
  clearError: vi.fn(),
  onSave: vi.fn().mockResolvedValue(undefined),
  ...overrides,
});

describe("BusinessTab", () => {
  it("renders the Business Details heading", () => {
    renderWithProviders(<BusinessTab {...makeProps()} />);
    expect(
      screen.getByRole("heading", { name: /Business Details/i })
    ).toBeInTheDocument();
  });

  it("renders all key business identity fields", () => {
    renderWithProviders(<BusinessTab {...makeProps()} />);
    expect(screen.getByDisplayValue("Test Restaurant")).toBeInTheDocument();
    expect(screen.getByDisplayValue("italian")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Owner")).toBeInTheDocument();
  });

  it("renders inline error messages from the errors prop", () => {
    renderWithProviders(
      <BusinessTab
        {...makeProps({ errors: { name: "Business name is required." } })}
      />
    );
    expect(screen.getByText(/Business name is required/i)).toBeInTheDocument();
  });

  it("calls setRestaurant when the name input changes", async () => {
    const user = userEvent.setup();
    const setRestaurant = vi.fn();
    renderWithProviders(<BusinessTab {...makeProps({ setRestaurant })} />);

    const nameInput = screen.getByDisplayValue("Test Restaurant");
    await user.clear(nameInput);
    await user.type(nameInput, "N");
    expect(setRestaurant).toHaveBeenCalled();
  });

  it("calls clearError when a field with an error is edited", async () => {
    const user = userEvent.setup();
    const clearError = vi.fn();
    renderWithProviders(
      <BusinessTab
        {...makeProps({
          errors: { name: "required" },
          clearError,
        })}
      />
    );

    const nameInput = screen.getByDisplayValue("Test Restaurant");
    await user.type(nameInput, "x");
    expect(clearError).toHaveBeenCalledWith("name");
  });
});
