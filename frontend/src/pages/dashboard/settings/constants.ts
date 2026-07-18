export const SUPPORTED_LANGUAGES = [
  { code: "en", label: "English" },
  { code: "te", label: "Telugu (తెలుగు)" },
  { code: "hi", label: "Hindi (हिंदी)" },
  { code: "es", label: "Spanish (Español)" },
] as const;

export const voiceOptions = [
  { id: "Leda",   name: "Leda - Warm",          accent: "American" },
  { id: "Kore",   name: "Kore - Professional",  accent: "American" },
  { id: "Aoede",  name: "Aoede - Friendly",     accent: "American" },
  { id: "Puck",   name: "Puck - Energetic",     accent: "American" },
  { id: "Zephyr", name: "Zephyr - Bright",      accent: "American" },
  { id: "Orus",   name: "Orus - Confident",     accent: "American" },
  { id: "Fenrir", name: "Fenrir - Calm",        accent: "American" },
  { id: "Charon", name: "Charon - Deep",        accent: "American" },
];

export const defaultHours = {
  monday:    { closed: false, last_call_offset_minutes: 0, periods: [{ open: "09:00", close: "21:00" }] },
  tuesday:   { closed: false, last_call_offset_minutes: 0, periods: [{ open: "09:00", close: "21:00" }] },
  wednesday: { closed: false, last_call_offset_minutes: 0, periods: [{ open: "09:00", close: "21:00" }] },
  thursday:  { closed: false, last_call_offset_minutes: 0, periods: [{ open: "09:00", close: "21:00" }] },
  friday:    { closed: false, last_call_offset_minutes: 0, periods: [{ open: "09:00", close: "22:00" }] },
  saturday:  { closed: false, last_call_offset_minutes: 0, periods: [{ open: "09:00", close: "22:00" }] },
  sunday:    { closed: false, last_call_offset_minutes: 0, periods: [{ open: "09:00", close: "20:00" }] },
};

// Canonical, UI-friendly view of one day's hours. Reads BOTH the new shape
// ({closed, last_call_offset_minutes, periods:[...]}) and the OLD shape
// ({closed, open, close}) so the editor can render existing configs unchanged.
export interface NormalizedDayHours {
  closed: boolean;
  last_call_offset_minutes: number;
  periods: { open: string; close: string }[];
}

export function normalizeDayHours(day: unknown): NormalizedDayHours {
  const d = (day || {}) as Record<string, unknown>;
  const closed = Boolean(d.closed);
  const rawOffset = Number(d.last_call_offset_minutes ?? 0);
  const offset = Number.isFinite(rawOffset) && rawOffset > 0 ? Math.floor(rawOffset) : 0;

  let periods: { open: string; close: string }[];
  if (Array.isArray(d.periods)) {
    periods = (d.periods as Record<string, string>[]).map((p) => ({
      open: p?.open ?? "",
      close: p?.close ?? "",
    }));
  } else if (d.open || d.close) {
    // Old single open/close pair → one period.
    periods = [{ open: (d.open as string) ?? "", close: (d.close as string) ?? "" }];
  } else {
    periods = [{ open: "09:00", close: "17:00" }];
  }

  return { closed, last_call_offset_minutes: offset, periods };
}

export const days: [keyof typeof defaultHours, string][] = [
  ["monday", "Monday"], ["tuesday", "Tuesday"], ["wednesday", "Wednesday"],
  ["thursday", "Thursday"], ["friday", "Friday"], ["saturday", "Saturday"],
  ["sunday", "Sunday"],
];

export const APPOINTMENT_TYPES = ["clinic", "salon", "home_services", "legal"];

export const getBusinessLabel = (businessType: string) => {
  switch (businessType) {
    case "clinic": return "Clinic";
    case "salon": return "Salon";
    case "home_services": return "Business";
    case "legal": return "Office";
    default: return "Restaurant";
  }
};

export const getSpecialtyLabel = (businessType: string) => {
  switch (businessType) {
    case "clinic": return "Specialty / Focus Area";
    case "salon": return "Specialty";
    case "home_services": return "Service Type";
    case "legal": return "Practice Area";
    default: return "Cuisine Type";
  }
};

export type FieldErrors = Record<string, string>;