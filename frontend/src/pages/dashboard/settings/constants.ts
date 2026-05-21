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
  monday:    { closed: false, open: "09:00", close: "21:00" },
  tuesday:   { closed: false, open: "09:00", close: "21:00" },
  wednesday: { closed: false, open: "09:00", close: "21:00" },
  thursday:  { closed: false, open: "09:00", close: "21:00" },
  friday:    { closed: false, open: "09:00", close: "22:00" },
  saturday:  { closed: false, open: "09:00", close: "22:00" },
  sunday:    { closed: false, open: "09:00", close: "20:00" },
};

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