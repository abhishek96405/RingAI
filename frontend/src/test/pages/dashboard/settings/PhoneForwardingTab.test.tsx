import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/utils/render";

// Mock the API module so we can assert call counts + arguments without
// going through MSW. We still import the real component under test.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    updateRestaurant: vi.fn().mockResolvedValue({ data: {} }),
    updateConfig: vi.fn().mockResolvedValue({ data: {} }),
  };
});

import PhoneForwardingTab from "@/pages/dashboard/settings/PhoneForwardingTab";
import { updateConfig, updateRestaurant } from "@/lib/api";

const AI_NUMBER = "+15555550100";
const BUSINESS_NUMBER = "+15555550101";
const ESCALATION_NUMBER = "+15555550199";

const makeProps = (
  overrides: Partial<Parameters<typeof PhoneForwardingTab>[0]> = {},
) => ({
  restaurantId: "tenant_a_restaurant",
  restaurant: {
    name: "Bella Cucina",
    phone_number: AI_NUMBER,
    business_phone: BUSINESS_NUMBER,
  },
  setRestaurant: vi.fn(),
  config: { escalation_phone_number: ESCALATION_NUMBER },
  setConfig: vi.fn(),
  onAfterSave: vi.fn().mockResolvedValue(undefined),
  ...overrides,
});

describe("PhoneForwardingTab", () => {
  beforeEach(() => {
    vi.mocked(updateRestaurant).mockClear();
    vi.mocked(updateConfig).mockClear();
    vi.mocked(updateRestaurant).mockResolvedValue({ data: {} } as never);
    vi.mocked(updateConfig).mockResolvedValue({ data: {} } as never);
  });

  it("renders all three phone fields with correct initial values", () => {
    renderWithProviders(<PhoneForwardingTab {...makeProps()} />);
    expect(screen.getByLabelText(/duuutah ai number/i)).toHaveValue(AI_NUMBER);
    expect(screen.getByLabelText(/^business phone$/i)).toHaveValue(BUSINESS_NUMBER);
    expect(screen.getByLabelText(/^escalation phone$/i)).toHaveValue(ESCALATION_NUMBER);
  });

  it("Save Changes triggers both PUT endpoints only when both fields change", async () => {
    const user = userEvent.setup();
    const setRestaurant = vi.fn();
    const setConfig = vi.fn();

    // Render with edited values (parent's state already moved past baseline).
    const editedBusiness = "+15555550199";  // change from BUSINESS_NUMBER
    const editedEscalation = "+15555550101"; // change from ESCALATION_NUMBER
    const { rerender } = renderWithProviders(
      <PhoneForwardingTab {...makeProps({ setRestaurant, setConfig })} />,
    );

    // Type into business — but onChange calls parent's setter, so we
    // simulate the parent re-rendering with the new value.
    const businessInput = screen.getByLabelText(/^business phone$/i);
    await user.clear(businessInput);
    await user.type(businessInput, editedBusiness);

    rerender(
      <PhoneForwardingTab
        {...makeProps({
          restaurant: {
            name: "Bella Cucina",
            phone_number: AI_NUMBER,
            business_phone: editedBusiness,
          },
          config: { escalation_phone_number: editedEscalation },
          setRestaurant,
          setConfig,
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(vi.mocked(updateRestaurant)).toHaveBeenCalledTimes(1);
    });
    expect(vi.mocked(updateRestaurant)).toHaveBeenCalledWith(
      "tenant_a_restaurant",
      { business_phone: editedBusiness },
    );
    expect(vi.mocked(updateConfig)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(updateConfig)).toHaveBeenCalledWith(
      "tenant_a_restaurant",
      { escalation_phone_number: editedEscalation },
    );
  });

  it("does not PUT when nothing has changed", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PhoneForwardingTab {...makeProps()} />);
    await user.click(screen.getByRole("button", { name: /save changes/i }));
    // Allow any in-flight promise microtasks to settle.
    await waitFor(() => {
      expect(vi.mocked(updateRestaurant)).not.toHaveBeenCalled();
    });
    expect(vi.mocked(updateConfig)).not.toHaveBeenCalled();
  });

  it("displays backend 400 error message when distinctness fails", async () => {
    const user = userEvent.setup();
    const setRestaurant = vi.fn();
    const errorDetail =
      "business_phone and phone_number must be different phone numbers " +
      "(both resolve to +15555550100). The AI DID, the publicly listed " +
      "business number, and the escalation number must all be distinct.";

    vi.mocked(updateRestaurant).mockRejectedValueOnce({
      response: { data: { detail: errorDetail } },
    });

    const { rerender } = renderWithProviders(
      <PhoneForwardingTab {...makeProps({ setRestaurant })} />,
    );

    // Simulate the user editing business_phone to match the AI DID.
    rerender(
      <PhoneForwardingTab
        {...makeProps({
          restaurant: {
            name: "Bella Cucina",
            phone_number: AI_NUMBER,
            business_phone: AI_NUMBER,
          },
          setRestaurant,
        })}
      />,
    );

    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/Phone numbers must be distinct/i),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/both resolve to/i)).toBeInTheDocument();

    // Conflicted inputs should pick up the destructive border via aria-invalid.
    expect(screen.getByLabelText(/^business phone$/i)).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    expect(screen.getByLabelText(/duuutah ai number/i)).toHaveAttribute(
      "aria-invalid",
      "true",
    );
    // Escalation isn't named in the message, so it stays untouched.
    expect(
      screen.getByLabelText(/^escalation phone$/i),
    ).not.toHaveAttribute("aria-invalid", "true");
  });

  it("carrier selector switches displayed instructions", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PhoneForwardingTab {...makeProps()} />);

    // Verizon (default first tab) — *72 should appear somewhere in steps.
    expect(screen.getAllByText(/\*72/).length).toBeGreaterThan(0);

    // Click AT&T tab.
    await user.click(screen.getByRole("tab", { name: /AT&T Wireless/i }));

    // AT&T uses **21*{number}#.
    await waitFor(() => {
      expect(screen.getAllByText(/\*\*21\*/i).length).toBeGreaterThan(0);
    });
  });

  it("substitutes {AI number} placeholder with the real DID", () => {
    renderWithProviders(<PhoneForwardingTab {...makeProps()} />);
    // Default carrier (Verizon) has "dial your Duuutah AI number: {AI number}".
    // After substitution the AI_NUMBER must appear in step text.
    const matches = screen.getAllByText((_, node) =>
      Boolean(node?.textContent?.includes(AI_NUMBER)),
    );
    expect(matches.length).toBeGreaterThan(0);
  });

  it("verification section shows business_phone when populated", () => {
    renderWithProviders(<PhoneForwardingTab {...makeProps()} />);
    // Verification section names the business phone in the dial step.
    const verifyHeading = screen.getByRole("heading", {
      name: /verify your forwarding works/i,
    });
    expect(verifyHeading).toBeInTheDocument();
    expect(screen.getByText(BUSINESS_NUMBER)).toBeInTheDocument();
  });

  it("verification section shows 'set numbers first' when business_phone is empty", () => {
    renderWithProviders(
      <PhoneForwardingTab
        {...makeProps({
          restaurant: { name: "Bella", phone_number: AI_NUMBER, business_phone: "" },
        })}
      />,
    );
    expect(
      screen.getByText(/Set your phone numbers in Section 1 first/i),
    ).toBeInTheDocument();
  });

  it("copy button writes the AI number to the clipboard", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    // jsdom defines navigator.clipboard as a getter — redefine the whole
    // property so vitest can install our stub.
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    renderWithProviders(<PhoneForwardingTab {...makeProps()} />);
    await user.click(screen.getByRole("button", { name: /copy ai number/i }));

    expect(writeText).toHaveBeenCalledWith(AI_NUMBER);
  });
});
