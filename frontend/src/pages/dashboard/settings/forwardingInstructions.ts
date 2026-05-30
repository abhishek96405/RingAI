export interface CarrierInstructions {
  id: string;
  label: string;
  activationSteps: string[];
  deactivationSteps: string[];
  notes?: string;
}

export const CARRIERS: CarrierInstructions[] = [
  {
    id: "verizon",
    label: "Verizon Wireless",
    activationSteps: [
      "On the business phone, open the keypad.",
      "Dial *72 and wait for the dial tone.",
      "After the tone, dial your Duuutah AI number: {AI number}.",
      "Press Send. The AI may answer briefly to confirm forwarding — that's expected, hang up.",
      "Test by calling your business phone from another phone (see Verify section below).",
    ],
    deactivationSteps: [
      "On the business phone, dial *73.",
      "Press Send. Listen for the confirmation tone.",
    ],
    notes: "Verizon's *72 is unconditional forwarding — every call routes to the AI until you dial *73.",
  },
  {
    id: "att",
    label: "AT&T Wireless",
    activationSteps: [
      "On the business phone, open the keypad.",
      "Dial **21*{AI number}# (include the * and # exactly as shown).",
      "Press Send. You should see a confirmation message or hear a tone.",
      "Test by calling your business phone from another phone.",
    ],
    deactivationSteps: [
      "On the business phone, dial ##21#.",
      "Press Send. Forwarding is now disabled.",
    ],
    notes: "AT&T uses the GSM forwarding standard. Include the full E.164 number (with the leading + if your handset shows the option).",
  },
  {
    id: "tmobile",
    label: "T-Mobile / Sprint",
    activationSteps: [
      "On the business phone, open the keypad.",
      "Dial **21*{AI number}# (include the * and # exactly as shown).",
      "Press Send. Wait for the confirmation message.",
      "Test by calling your business phone from another phone.",
    ],
    deactivationSteps: [
      "On the business phone, dial ##21#.",
      "Press Send. Forwarding is now disabled.",
    ],
    notes: "T-Mobile absorbed Sprint — the same codes work for legacy Sprint lines.",
  },
  {
    id: "spectrum",
    label: "Spectrum (landline)",
    activationSteps: [
      "Pick up your business phone and listen for a dial tone.",
      "Dial *72.",
      "After the second dial tone, dial your Duuutah AI number: {AI number}.",
      "Wait for the confirmation tone (two short beeps), then hang up.",
      "Test by calling your business phone from another phone.",
    ],
    deactivationSteps: [
      "Pick up your business phone and listen for a dial tone.",
      "Dial *73. Wait for the confirmation tone, then hang up.",
    ],
    notes: "If you don't hear a second dial tone after *72, the feature may not be on your Spectrum plan. Call Spectrum support and ask to enable Call Forwarding (Variable).",
  },
  {
    id: "xfinity",
    label: "Xfinity / Comcast Voice",
    activationSteps: [
      "Sign in at xfinity.com/voice with the Xfinity ID on the account.",
      "Open Settings → Call Forwarding.",
      "Choose Forward All Calls and enter your Duuutah AI number: {AI number}.",
      "Save. Forwarding is active immediately.",
      "Test by calling your business phone from another phone.",
    ],
    deactivationSteps: [
      "Sign in at xfinity.com/voice.",
      "Open Settings → Call Forwarding and switch Forward All Calls to Off.",
    ],
    notes: "Xfinity Voice manages forwarding from the portal, not from the handset. The *72 / *73 codes will not work on most Xfinity Voice lines.",
  },
  {
    id: "google_voice",
    label: "Google Voice",
    activationSteps: [
      "Sign in at voice.google.com with the Google account that owns the business number.",
      "Open Settings → Phone Numbers.",
      "Make sure your Duuutah AI number is the only linked number, or that it's marked as the primary forwarding target.",
      "Disable any other linked phones so calls don't ring elsewhere.",
      "Test by calling your Google Voice number from another phone.",
    ],
    deactivationSteps: [
      "Open Settings → Phone Numbers at voice.google.com.",
      "Remove the Duuutah AI number from your linked numbers, or re-enable your previous device.",
    ],
    notes: "Google Voice can't dial *72. All forwarding is managed in the web settings.",
  },
  {
    id: "other",
    label: "Other carrier",
    activationSteps: [
      "On the business phone, dial *72 and wait for a second dial tone.",
      "After the tone, dial your Duuutah AI number: {AI number}.",
      "Press Send. Listen for a confirmation tone, then hang up.",
      "Test by calling your business phone from another phone.",
      "If *72 doesn't work, contact your carrier and ask them to enable unconditional call forwarding to {AI number}.",
    ],
    deactivationSteps: [
      "On the business phone, dial *73 and press Send.",
      "If *73 doesn't work, ask your carrier to disable call forwarding on the line.",
    ],
    notes: "*72 / *73 is the most common North American pattern. Some VoIP and prepaid carriers manage forwarding only from a web portal or customer service line.",
  },
];
