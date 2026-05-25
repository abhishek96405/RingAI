import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/utils/render";
import HoursTab from "@/pages/dashboard/settings/HoursTab";
import { defaultHours } from "@/pages/dashboard/settings/constants";

const makeProps = (overrides: Partial<Parameters<typeof HoursTab>[0]> = {}) => ({
  config: { operating_hours: defaultHours, after_hours_mode: "voicemail" },
  setConfig: vi.fn(),
  saving: false,
  onSave: vi.fn().mockResolvedValue(undefined),
  ...overrides,
});

describe("HoursTab", () => {
  it("renders the Hours & Availability heading", () => {
    renderWithProviders(<HoursTab {...makeProps()} />);
    expect(
      screen.getByRole("heading", { name: /Hours & Availability/i })
    ).toBeInTheDocument();
  });

  it("renders a row for each weekday", () => {
    renderWithProviders(<HoursTab {...makeProps()} />);
    expect(screen.getByText("Monday")).toBeInTheDocument();
    expect(screen.getByText("Tuesday")).toBeInTheDocument();
    expect(screen.getByText("Wednesday")).toBeInTheDocument();
    expect(screen.getByText("Thursday")).toBeInTheDocument();
    expect(screen.getByText("Friday")).toBeInTheDocument();
    expect(screen.getByText("Saturday")).toBeInTheDocument();
    expect(screen.getByText("Sunday")).toBeInTheDocument();
  });

  it("calls onSave when the Save Hours button is clicked", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(<HoursTab {...makeProps({ onSave })} />);

    await user.click(screen.getByRole("button", { name: /save hours/i }));
    expect(onSave).toHaveBeenCalled();
  });

  it("calls setConfig when a closed checkbox is toggled", async () => {
    const user = userEvent.setup();
    const setConfig = vi.fn();
    renderWithProviders(<HoursTab {...makeProps({ setConfig })} />);

    const checkboxes = screen.getAllByRole("checkbox");
    await user.click(checkboxes[0]);
    expect(setConfig).toHaveBeenCalled();
  });

  it("disables Save while saving", () => {
    renderWithProviders(<HoursTab {...makeProps({ saving: true })} />);
    expect(screen.getByRole("button", { name: /saving/i })).toBeDisabled();
  });
});
