import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "@/test/utils/render";
import VoiceAndAITab from "@/pages/dashboard/settings/VoiceAndAITab";

const makeProps = (overrides: Partial<Parameters<typeof VoiceAndAITab>[0]> = {}) => ({
  restaurant: { plan: "PRO" },
  config: {
    persona: "friendly",
    custom_greeting: "Hello from Duuutah AI",
    voice_id: "alloy",
    language: "en",
  },
  setConfig: vi.fn(),
  saving: false,
  onSave: vi.fn().mockResolvedValue(undefined),
  ...overrides,
});

describe("VoiceAndAITab", () => {
  it("renders the Voice & AI heading", () => {
    renderWithProviders(<VoiceAndAITab {...makeProps()} />);
    expect(
      screen.getByRole("heading", { name: /Voice & AI/i })
    ).toBeInTheDocument();
  });

  it("renders an AI Persona label and select", () => {
    renderWithProviders(<VoiceAndAITab {...makeProps()} />);
    expect(screen.getByText(/AI Persona/i)).toBeInTheDocument();
  });

  it("invokes onSave when the Save button is clicked", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(<VoiceAndAITab {...makeProps({ onSave })} />);

    const saveBtn = screen
      .getAllByRole("button")
      .find((b) => /save/i.test(b.textContent ?? ""));
    expect(saveBtn).toBeDefined();
    await user.click(saveBtn!);
    expect(onSave).toHaveBeenCalled();
  });

  it("disables Save while saving", () => {
    renderWithProviders(<VoiceAndAITab {...makeProps({ saving: true })} />);
    const savingBtn = screen
      .getAllByRole("button")
      .find((b) => /saving/i.test(b.textContent ?? ""));
    expect(savingBtn).toBeDefined();
    expect(savingBtn).toBeDisabled();
  });
});
