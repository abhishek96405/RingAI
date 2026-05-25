import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/utils/render";
import RulesTab from "@/pages/dashboard/settings/RulesTab";

const makeProps = (overrides: Partial<Parameters<typeof RulesTab>[0]> = {}) => ({
  config: { business_rules: [], escalation_rules: [] },
  setConfig: vi.fn(),
  saving: false,
  onSave: vi.fn().mockResolvedValue(undefined),
  ...overrides,
});

describe("RulesTab", () => {
  it("renders Business Rules and Escalation Triggers cards", () => {
    renderWithProviders(<RulesTab {...makeProps()} />);
    expect(
      screen.getByRole("heading", { name: /Business Rules/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /Escalation Triggers/i })
    ).toBeInTheDocument();
  });

  it("appends a rule when Add is clicked with text in the input", async () => {
    const user = userEvent.setup();
    const setConfig = vi.fn();
    renderWithProviders(<RulesTab {...makeProps({ setConfig })} />);

    const input = screen.getByPlaceholderText(/Add a business rule/i);
    await user.type(input, "No splitting checks");

    const addBtns = screen.getAllByRole("button").filter(
      (b) => b.querySelector("svg") !== null && !/save|saving/i.test(b.textContent ?? "")
    );
    await user.click(addBtns[0]);

    expect(setConfig).toHaveBeenCalledWith(
      expect.objectContaining({
        business_rules: expect.arrayContaining(["No splitting checks"]),
      })
    );
  });

  it("ignores adding an empty rule", async () => {
    const user = userEvent.setup();
    const setConfig = vi.fn();
    renderWithProviders(<RulesTab {...makeProps({ setConfig })} />);

    const addBtns = screen.getAllByRole("button").filter(
      (b) => b.querySelector("svg") !== null && !/save|saving/i.test(b.textContent ?? "")
    );
    await user.click(addBtns[0]);
    expect(setConfig).not.toHaveBeenCalled();
  });

  it("renders existing business rules and escalation triggers", () => {
    renderWithProviders(
      <RulesTab
        {...makeProps({
          config: {
            business_rules: ["No splitting checks", "Max party size 10"],
            escalation_rules: ["Allergy emergency"],
          },
        })}
      />
    );
    expect(screen.getByText(/No splitting checks/i)).toBeInTheDocument();
    expect(screen.getByText(/Max party size 10/i)).toBeInTheDocument();
    expect(screen.getByText(/Allergy emergency/i)).toBeInTheDocument();
  });

  it("calls onSave when Save Rules is clicked", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(<RulesTab {...makeProps({ onSave })} />);

    await user.click(screen.getByRole("button", { name: /save rules/i }));
    expect(onSave).toHaveBeenCalled();
  });
});
