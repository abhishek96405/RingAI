import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  activateRestaurant,
  confirmMenu,
  createBillingCheckout,
  createRestaurant as createRestaurantApi,
  parseMenu as parseMenuApi,
  setRestaurantId as persistRestaurantId,
  updateConfig,
} from "@/lib/api";
import { useAppSession } from "@/context/AppSessionContext";
import {
  Building2,
  Check,
  CreditCard,
  Phone,
  Settings,
  Utensils,
  ArrowLeft,
  ArrowRight,
  LogOut,
  Briefcase,
  Scissors,
  Zap,
} from "lucide-react";
import { SignOutButton } from "@clerk/clerk-react";
import { AnimatePresence, motion } from "framer-motion";
import { toast } from "sonner";
import { getApiErrorMessage } from "@/lib/errors";
import type { Restaurant, Config, MenuItem } from "@/types";

// Business type options for horizontal platform
const businessTypeOptions = [
  { value: "restaurant", label: "Restaurant / Food Service", icon: Utensils, description: "Restaurants, cafes, food trucks, catering" },
  { value: "salon", label: "Salon / Beauty", icon: Scissors, description: "Hair salons, spas, nail studios, barbershops" },
];

const steps = [
  { icon: Briefcase, label: "Business Type" },
  { icon: Building2, label: "Business Info" },
  { icon: Utensils, label: "Menu / Services" },
  { icon: Settings, label: "AI Configuration" },
  { icon: CreditCard, label: "Choose Plan" },
];

const defaultHours = {
  monday: { closed: false, open: "09:00", close: "21:00" },
  tuesday: { closed: false, open: "09:00", close: "21:00" },
  wednesday: { closed: false, open: "09:00", close: "21:00" },
  thursday: { closed: false, open: "09:00", close: "21:00" },
  friday: { closed: false, open: "09:00", close: "22:00" },
  saturday: { closed: false, open: "09:00", close: "22:00" },
  sunday: { closed: false, open: "09:00", close: "20:00" },
};

const days: [keyof typeof defaultHours, string][] = [
  ["monday", "Monday"],
  ["tuesday", "Tuesday"],
  ["wednesday", "Wednesday"],
  ["thursday", "Thursday"],
  ["friday", "Friday"],
  ["saturday", "Saturday"],
  ["sunday", "Sunday"],
];

export default function Onboarding() {
  const navigate = useNavigate();
  const { activeRestaurant, onboardingComplete, refreshSession, setActiveRestaurant } =
    useAppSession();

  const lastHydratedRestaurantId = useRef<string | null>(null);

  const [currentStep, setCurrentStep] = useState(0);
  const [selectedPlan, setSelectedPlan] = useState<"STARTER" | "PRO">("PRO");
  const [restaurantId, setRestaurantId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [activating, setActivating] = useState(false);

  // Business type — read from localStorage if pre-selected from landing page
  const [businessType, setBusinessType] = useState<string>(() => {
    const preSelected = localStorage.getItem("ringai_selected_business_type");
    if (preSelected && ["restaurant", "salon"].includes(preSelected)) {
      return preSelected;
    }
    return "restaurant";
  });

  const [restaurantData, setRestaurantData] = useState<Restaurant>({
    name: "",
    cuisine_type: "",
    address: "",
    _street: "",
    _city: "",
    _state: "",
    _zip: "",
    timezone: "America/Chicago",
    owner_name: "",
    owner_email: "",
    owner_phone: "",
    billing_email: "",
    business_phone: "",
    website: "",
    primary_language: "en",
    pickup_enabled: true,
    delivery_enabled: true,
    dine_in_enabled: true,
    reservations_enabled: true,
    offers_delivery: true,
    offers_reservations: true,
    catering_enabled: false,
    avg_prep_time_minutes: 20,
    reservation_party_limit: 8,
  });

  const [menuText, setMenuText] = useState("");
  const [parsedItems, setParsedItems] = useState<MenuItem[]>([]);
  const [aiConfig, setAiConfig] = useState<Config>({
    persona: "friendly",
    disclosure_text: "",
    upsell_enabled: true,
    primary_language: "en",
    after_hours_mode: "voicemail",
    voicemail_enabled: true,
    escalation_phone_number: "",
    operating_hours: defaultHours,
  });

  // Derived helpers
  const isAppointmentBusiness = businessType === "salon";

  const getBusinessLabel = () => {
    switch (businessType) {
      case "clinic": return "Clinic";
      case "salon": return "Salon";
      case "home_services": return "Business";
      case "legal": return "Office";
      default: return "Restaurant";
    }
  };

  const getSpecialtyLabel = () => {
    switch (businessType) {
      case "clinic": return "Specialty (e.g. Family Medicine, Dental)";
      case "salon": return "Specialty (e.g. Hair, Nails, Spa)";
      case "home_services": return "Service Type (e.g. HVAC, Plumbing)";
      case "legal": return "Practice Area (e.g. Family Law)";
      default: return "Cuisine Type (e.g. Italian, Mexican)";
    }
  };

  useEffect(() => {
    if (!activeRestaurant?.id) return;
    if (lastHydratedRestaurantId.current === activeRestaurant.id) return;

    lastHydratedRestaurantId.current = activeRestaurant.id;
    setRestaurantId(activeRestaurant.id);

    setRestaurantData((prev) => ({
      ...prev,
      ...activeRestaurant,
      timezone: activeRestaurant.timezone || "America/Chicago",
      primary_language: activeRestaurant.primary_language || "en",
    }));

    setAiConfig((prev) => ({
      ...prev,
      primary_language: activeRestaurant.primary_language || prev.primary_language || "en",
      disclosure_text:
        prev.disclosure_text ||
        `Hi! I'm an AI assistant for ${activeRestaurant.name || "your business"}. How can I help you today?`,
      operating_hours: {
        ...defaultHours,
        ...(prev.operating_hours || {}),
      },
    }));

    if (activeRestaurant.is_active) {
      setCurrentStep(4);
    }
  }, [activeRestaurant]);

  useEffect(() => {
    if (activeRestaurant && onboardingComplete) {
      navigate("/dashboard", { replace: true });
    }
  }, [activeRestaurant, onboardingComplete, navigate]);

  const createRestaurant = async () => {
    if (!restaurantData.name.trim()) {
      toast.error(`${getBusinessLabel()} name is required`);
      return;
    }
    if (!restaurantData._street?.trim() || !restaurantData._city?.trim() || !restaurantData._state?.trim() || !restaurantData._zip?.trim()) {
      toast.error("Complete business address is required (street, city, state, zip)");
      return;
    }

    setSubmitting(true);
    try {
      restaurantData.address = `${restaurantData._street}, ${restaurantData._city}, ${restaurantData._state} ${restaurantData._zip}`;
      restaurantData.business_type = businessType;
      const res = await createRestaurantApi(restaurantData);
      const createdRestaurant = res.data;

      setRestaurantId(createdRestaurant.id);
      persistRestaurantId(createdRestaurant.id);
      setActiveRestaurant(createdRestaurant);

      // Save business_type to config immediately
      try {
        await updateConfig(createdRestaurant.id, { business_type: businessType });
      } catch (e) {
        console.warn("Could not set business_type in config", e);
      }

      setAiConfig((prev) => ({
        ...prev,
        primary_language: createdRestaurant.primary_language || "en",
        disclosure_text:
          prev.disclosure_text?.trim() ||
          `Hi! I'm an AI assistant for ${createdRestaurant.name}. How can I help you today?`,
      }));

      toast.success(`${getBusinessLabel()} created!`);
      setCurrentStep(2);
    } catch (err) {
      toast.error(getApiErrorMessage(err, `Failed to create ${getBusinessLabel().toLowerCase()}`));
    } finally {
      setSubmitting(false);
    }
  };

  const parseMenu = async () => {
    if (!restaurantId) {
      toast.error(`Create your ${getBusinessLabel().toLowerCase()} first`);
      setCurrentStep(1);
      return;
    }

    if (!menuText.trim()) {
      toast.error(`Please enter your ${isAppointmentBusiness ? "services" : "menu"} text`);
      return;
    }

    setParsing(true);
    try {
      const res = await parseMenuApi({ menu_text: menuText, restaurant_id: restaurantId });
      setParsedItems(res.data.items || []);
      if (res.data.items?.length > 0) {
        toast.success(`Parsed ${res.data.items.length} items!`);
      } else {
        toast.warning("No items could be parsed. Try a different format.");
      }
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to parse"));
    } finally {
      setParsing(false);
    }
  };

  const saveMenuAndProceed = async () => {
    if (!restaurantId) {
      toast.error(`Create your ${getBusinessLabel().toLowerCase()} first`);
      setCurrentStep(1);
      return;
    }
    if (parsedItems.length === 0) {
      toast.warning(`Parse your ${isAppointmentBusiness ? "services" : "menu"} first`);
      return;
    }

    setSubmitting(true);
    try {
      await confirmMenu(restaurantId, parsedItems);
      toast.success(`${isAppointmentBusiness ? "Services" : "Menu"} saved!`);
      setCurrentStep(3);
    } catch (err) {
      toast.error(getApiErrorMessage(err, `Failed to save ${isAppointmentBusiness ? "services" : "menu"}`));
    } finally {
      setSubmitting(false);
    }
  };

  const saveConfigAndProceed = async () => {
    if (!restaurantId) {
      toast.error(`Create your ${getBusinessLabel().toLowerCase()} first`);
      setCurrentStep(1);
      return;
    }

    setSubmitting(true);
    try {
      await updateConfig(restaurantId, aiConfig);
      toast.success("AI configuration saved!");
      setCurrentStep(4);
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to save config"));
    } finally {
      setSubmitting(false);
    }
  };

  const goLive = async () => {
    if (!restaurantId) {
      toast.error(`Create your ${getBusinessLabel().toLowerCase()} first`);
      setCurrentStep(1);
      return;
    }

    setActivating(true);
    try {
      const res = await createBillingCheckout({
        restaurant_id: restaurantId,
        plan: selectedPlan,
        source: "onboarding",
      });
      window.location.href = res.data.checkout_url;
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to start checkout"));
      setActivating(false);
    }
  };

  const updateHours = (dayKey: keyof typeof defaultHours, field: string, value: string | boolean) => {
    setAiConfig((prev) => ({
      ...prev,
      operating_hours: {
        ...prev.operating_hours,
        [dayKey]: { ...prev.operating_hours[dayKey], [field]: value },
      },
    }));
  };

  const handleNext = async () => {
    if (submitting || parsing || activating) return;

    if (currentStep === 0) {
      localStorage.removeItem("ringai_selected_business_type");
      setCurrentStep(1);
      return;
    }
    if (currentStep === 1) { await createRestaurant(); return; }
    if (currentStep === 2) { await saveMenuAndProceed(); return; }
    if (currentStep === 3) { await saveConfigAndProceed(); return; }
    await goLive();
  };

  const handleBack = () => {
    if (submitting || parsing || activating) return;
    setCurrentStep((prev) => Math.max(0, prev - 1));
  };

  const renderStep = () => {
    switch (currentStep) {

      // ── STEP 0: Business Type ──
      case 0:
        return (
          <div className="space-y-6">
            <div className="text-center mb-6">
              <h3 className="text-lg font-semibold mb-2">What type of business are you?</h3>
              <p className="text-sm text-ink-soft">This helps us customize the AI assistant for your needs</p>
            </div>
            <div className="grid gap-3">
              {businessTypeOptions.map((option) => {
                const Icon = option.icon;
                const isSelected = businessType === option.value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setBusinessType(option.value)}
                    className={`flex items-center gap-4 p-4 rounded-xl border-2 transition-all text-left ${
                      isSelected
                        ? "border-primary bg-primary/10"
                        : "border-line hover:border-primary/40 bg-cream"
                    }`}
                  >
                    <div className={`p-3 rounded-lg ${isSelected ? "bg-primary/20" : "bg-muted/50"}`}>
                      <Icon className={`w-6 h-6 ${isSelected ? "text-primary" : "text-ink-soft"}`} />
                    </div>
                    <div className="flex-1">
                      <div className={`font-medium ${isSelected ? "text-foreground" : "text-foreground/80"}`}>
                        {option.label}
                      </div>
                      <div className="text-sm text-ink-soft">{option.description}</div>
                    </div>
                    {isSelected && <Check className="w-5 h-5 text-primary" />}
                  </button>
                );
              })}
            </div>
          </div>
        );

      // ── STEP 1: Business Info ──
      case 1:
        return (
          <div className="space-y-5">
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>{getBusinessLabel()} Name *</Label>
                <Input
                  value={restaurantData.name}
                  onChange={(e) => setRestaurantData({ ...restaurantData, name: e.target.value })}
                  className="h-11 rounded-xl"
                  placeholder={`Your ${getBusinessLabel()} name`}
                />
              </div>
              <div className="space-y-2">
                <Label>{businessType === "restaurant" ? "Cuisine Type" : "Specialty"}</Label>
                <Input
                  value={restaurantData.cuisine_type}
                  onChange={(e) => setRestaurantData({ ...restaurantData, cuisine_type: e.target.value })}
                  className="h-11 rounded-xl"
                  placeholder={getSpecialtyLabel()}
                />
              </div>
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Owner Name</Label>
                <Input value={restaurantData.owner_name} onChange={(e) => setRestaurantData({ ...restaurantData, owner_name: e.target.value })} className="h-11 rounded-xl" />
              </div>
              <div className="space-y-2">
                <Label>Owner Email</Label>
                <Input type="email" value={restaurantData.owner_email} onChange={(e) => setRestaurantData({ ...restaurantData, owner_email: e.target.value })} className="h-11 rounded-xl" />
              </div>
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Business Phone</Label>
                <Input value={restaurantData.business_phone} onChange={(e) => setRestaurantData({ ...restaurantData, business_phone: e.target.value })} className="h-11 rounded-xl" />
                <p className="text-xs text-ink-soft">We'll forward calls from this number to your Duuutah AI line. You can set up forwarding instructions in Settings after onboarding.</p>
              </div>
              <div className="space-y-2">
                <Label>Billing Email</Label>
                <Input type="email" value={restaurantData.billing_email} onChange={(e) => setRestaurantData({ ...restaurantData, billing_email: e.target.value })} className="h-11 rounded-xl" />
              </div>
            </div>

            <div className="space-y-2">
              <Label>Street Address <span className="text-destructive">*</span></Label>
              <Input 
                value={restaurantData._street} 
                onChange={(e) => setRestaurantData({ ...restaurantData, _street: e.target.value })} 
                className="h-11 rounded-xl" 
                placeholder="1520 W Ogden Ave"
              />
            </div>
            <div className="grid sm:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>City <span className="text-destructive">*</span></Label>
                <Input value={restaurantData._city} onChange={(e) => setRestaurantData({ ...restaurantData, _city: e.target.value })} placeholder="Naperville" className="h-11 rounded-xl" />
              </div>
              <div className="space-y-2">
                <Label>State <span className="text-destructive">*</span></Label>
                <Input value={restaurantData._state} onChange={(e) => setRestaurantData({ ...restaurantData, _state: e.target.value })} placeholder="IL" maxLength={2} className="h-11 rounded-xl" />
              </div>
              <div className="space-y-2">
                <Label>Zip Code <span className="text-destructive">*</span></Label>
                <Input value={restaurantData._zip} onChange={(e) => setRestaurantData({ ...restaurantData, _zip: e.target.value })} placeholder="60540" maxLength={5} className="h-11 rounded-xl" />
              </div>
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Timezone</Label>
                <div className="h-11 rounded-xl bg-cream border border-line flex items-center px-3 text-sm text-ink-soft">
                  Auto-detected from address
                </div>
              </div>
              <div className="space-y-2">
                <Label>Primary Language</Label>
                <Select value={restaurantData.primary_language} onValueChange={(v) => setRestaurantData({ ...restaurantData, primary_language: v })}>
                  <SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="en">English</SelectItem>
                    <SelectItem value="es">Spanish</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Restaurant-only fields */}
            {!isAppointmentBusiness && (
              <>
                <div className="grid sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Average Prep Time (minutes)</Label>
                    <Input type="number" value={restaurantData.avg_prep_time_minutes} onChange={(e) => setRestaurantData({ ...restaurantData, avg_prep_time_minutes: Number(e.target.value || 0) })} className="h-11 rounded-xl" />
                  </div>
                  <div className="space-y-2">
                    <Label>Reservation Party Limit</Label>
                    <Input type="number" value={restaurantData.reservation_party_limit} onChange={(e) => setRestaurantData({ ...restaurantData, reservation_party_limit: Number(e.target.value || 0) })} className="h-11 rounded-xl" />
                  </div>
                </div>
                <div className="grid sm:grid-cols-2 gap-4">
                  {[["pickup_enabled", "Pickup Enabled"], ["dine_in_enabled", "Dine-in Enabled"]].map(([key, label]) => (
                    <div key={key} className="flex items-center justify-between p-3 rounded-lg bg-cream">
                      <span className="text-sm">{label}</span>
                      <input type="checkbox" className="accent-primary" checked={restaurantData[key]} onChange={(e) => setRestaurantData({ ...restaurantData, [key]: e.target.checked })} />
                    </div>
                  ))}
                  {[
                    { key: "offers_delivery", label: "Does your restaurant offer delivery?" },
                    { key: "offers_reservations", label: "Does your restaurant take reservations?" },
                  ].map(({ key, label }) => (
                    <div key={key} className="flex items-center justify-between p-3 rounded-lg bg-cream">
                      <span className="text-sm">{label}</span>
                      <div className="flex gap-2">
                        <button type="button" onClick={() => setRestaurantData({ ...restaurantData, [key]: true })} className={`px-3 py-1 text-xs rounded-lg font-medium transition-colors ${restaurantData[key] ? "bg-primary text-primary-foreground" : "bg-line text-ink-soft"}`}>Yes</button>
                        <button type="button" onClick={() => setRestaurantData({ ...restaurantData, [key]: false })} className={`px-3 py-1 text-xs rounded-lg font-medium transition-colors ${!restaurantData[key] ? "bg-primary text-primary-foreground" : "bg-line text-ink-soft"}`}>No</button>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        );

      // ── STEP 2: Menu / Services ──
      case 2:
        return (
          <div className="space-y-5">
            <div className="space-y-2">
              <Label>{isAppointmentBusiness ? "Services Offered" : "Paste Menu Text"}</Label>
              <Textarea
                value={menuText}
                onChange={(e) => setMenuText(e.target.value)}
                className="rounded-xl min-h-[200px]"
                placeholder={
                  isAppointmentBusiness
                    ? `SERVICES\nHaircut - $35 - 30 min\nColor Treatment - $120 - 90 min\nDeep Conditioning - $45 - 45 min`
                    : `APPETIZERS\nBruschetta - $12.99\nCalamari - $14.99\n\nPASTA\nSpaghetti Bolognese - $18.99`
                }
              />
            </div>
            <Button type="button" variant="outline" className="rounded-xl" onClick={parseMenu} disabled={parsing || submitting}>
              {parsing ? "Parsing with AI..." : `Parse ${isAppointmentBusiness ? "Services" : "Menu"}`}
            </Button>

            {parsedItems.length > 0 && (
              <Card className="p-0 overflow-hidden border-line">
                <div className="p-3 bg-cream text-sm font-medium">{parsedItems.length} items parsed</div>
                <div className="divide-y divide-border max-h-72 overflow-y-auto">
                  {parsedItems.map((item, i: number) => (
                    <div key={i} className="flex items-center justify-between px-4 py-3 text-sm">
                      <div>
                        <p className="font-medium">{item.name}</p>
                        <p className="text-xs text-ink-soft">{item.category}</p>
                      </div>
                      <span>{item.price ? `$${(item.price / 100).toFixed(2)}` : "--"}</span>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        );

      // ── STEP 3: AI Configuration ──
      case 3:
        return (
          <div className="space-y-5">
            <div className="space-y-2">
              <Label>AI Persona</Label>
              <Select value={aiConfig.persona} onValueChange={(v) => setAiConfig({ ...aiConfig, persona: v })}>
                <SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="friendly">Friendly & Warm</SelectItem>
                  <SelectItem value="professional">Professional & Formal</SelectItem>
                  <SelectItem value="casual">Casual & Relaxed</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Greeting Message</Label>
              <Textarea value={aiConfig.disclosure_text} onChange={(e) => setAiConfig({ ...aiConfig, disclosure_text: e.target.value })} className="rounded-xl min-h-[80px]" />
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Primary Language</Label>
                <Select value={aiConfig.primary_language} onValueChange={(v) => setAiConfig({ ...aiConfig, primary_language: v })}>
                  <SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="en">English</SelectItem>
                    <SelectItem value="es">Spanish</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>After-hours Behavior</Label>
                <Select value={aiConfig.after_hours_mode} onValueChange={(v) => setAiConfig({ ...aiConfig, after_hours_mode: v })}>
                  <SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="voicemail">Take voicemail</SelectItem>
                    <SelectItem value="close_message">Play closed message</SelectItem>
                    <SelectItem value="forward">Forward to escalation number</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Escalation Phone Number</Label>
              <Input value={aiConfig.escalation_phone_number} onChange={(e) => setAiConfig({ ...aiConfig, escalation_phone_number: e.target.value })} className="h-11 rounded-xl" />
              <p className="text-xs text-ink-soft">This is the phone inside your business that rings when the AI hands off to a human. Must be different from your business phone.</p>
            </div>

            <div className="grid sm:grid-cols-2 gap-4">
              {/* Upselling — restaurant only */}
              {!isAppointmentBusiness && (
                <div className="flex items-center justify-between p-3 rounded-lg bg-cream">
                  <span className="text-sm">Enable Upselling</span>
                  <input type="checkbox" className="accent-primary" checked={aiConfig.upsell_enabled} onChange={(e) => setAiConfig({ ...aiConfig, upsell_enabled: e.target.checked })} />
                </div>
              )}
              <div className="flex items-center justify-between p-3 rounded-lg bg-cream">
                <span className="text-sm">Voicemail Enabled</span>
                <input type="checkbox" className="accent-primary" checked={aiConfig.voicemail_enabled} onChange={(e) => setAiConfig({ ...aiConfig, voicemail_enabled: e.target.checked })} />
              </div>
            </div>

            <div>
              <Label className="mb-3 block">Operating Hours</Label>
              <div className="space-y-3">
                {days.map(([key, label]) => {
                  const day = aiConfig.operating_hours[key];
                  return (
                    <div key={key} className="grid grid-cols-12 gap-2 items-center p-3 rounded-lg bg-cream">
                      <div className="col-span-3"><p className="text-sm font-medium">{label}</p></div>
                      <div className="col-span-2 flex items-center gap-2">
                        <input type="checkbox" className="accent-primary" checked={day.closed} onChange={(e) => updateHours(key, "closed", e.target.checked)} />
                        <span className="text-xs text-ink-soft">Closed</span>
                      </div>
                      <div className="col-span-3"><Input type="time" value={day.open} disabled={day.closed} onChange={(e) => updateHours(key, "open", e.target.value)} /></div>
                      <div className="col-span-1 text-center text-xs text-ink-soft">to</div>
                      <div className="col-span-3"><Input type="time" value={day.close} disabled={day.closed} onChange={(e) => updateHours(key, "close", e.target.value)} /></div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        );

      // ── STEP 4: Choose Plan ──
      case 4:
        return (
          <div className="space-y-5">
            <div className="grid sm:grid-cols-2 gap-4">
              {[
                { key: "STARTER" as const, name: "Starter", price: 199, calls: "500", overage: "0.30", features: ["AI order taking", "1 AI voice", "POS integration", "SMS confirmations", "Analytics dashboard", "Email support"] },
                { key: "PRO" as const, name: "Pro", price: 349, calls: "1,000", overage: "0.25", popular: true, features: ["Everything in Starter, plus:", "Delivery handling", "Table reservations", "AI upselling", "Customer recognition", "Auto AI learning", "8 AI voices (multi-language coming soon)", "Priority support"] },
              ].map((plan) => (
                <Card
                  key={plan.key}
                  className={`relative p-5 cursor-pointer transition-all ${
                    selectedPlan === plan.key
                      ? "border-primary shadow-glow ring-2 ring-primary/20"
                      : "border-line hover:border-primary/30"
                  }`}
                  onClick={() => setSelectedPlan(plan.key)}
                >
                  {plan.popular && (
                    <div className="absolute -top-2.5 left-1/2 -translate-x-1/2">
                      <Badge className="bg-gradient-primary text-primary-foreground text-[10px] px-2.5 py-0.5 border-0">Most Popular</Badge>
                    </div>
                  )}
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-display font-bold text-lg">{plan.name}</h3>
                    <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${selectedPlan === plan.key ? "border-primary bg-primary" : "border-muted-foreground/30"}`}>
                      {selectedPlan === plan.key && <Check className="w-3 h-3 text-primary-foreground" />}
                    </div>
                  </div>
                  <div className="mb-3">
                    <span className="text-3xl font-display font-bold">${plan.price}</span>
                    <span className="text-sm text-ink-soft">/month</span>
                  </div>
                  <p className="text-xs text-ink-soft mb-3">{plan.calls} calls/mo · ${plan.overage}/call overage</p>
                  <div className="space-y-1.5">
                    {plan.features.map((f, i) => (
                      <div key={i} className="flex items-start gap-2 text-xs">
                        <Check className="w-3.5 h-3.5 text-success mt-0.5 shrink-0" />
                        <span className="text-ink-soft">{f}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              ))}
            </div>
            <Card className="dash-card p-4 bg-primary/5 border-primary/20">
              <div className="flex items-center gap-3">
                <Zap className="w-5 h-5 text-primary" />
                <div>
                  <p className="text-sm font-medium">7-day free trial · No charge today</p>
                  <p className="text-xs text-ink-soft">Cancel anytime during the trial — you won't be billed</p>
                </div>
              </div>
            </Card>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="dash dash-surface min-h-screen flex flex-col">
      <div className="border-b border-line bg-card/80 backdrop-blur-xl">
        <div className="container-tight flex items-center justify-between h-16">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-gradient-primary flex items-center justify-center">
              <Phone className="w-4 h-4 text-primary-foreground" />
            </div>
            <div className="flex items-center gap-3">
              <span className="text-sm text-ink-soft">
                Step {currentStep + 1} of {steps.length}
              </span>
              <SignOutButton redirectUrl="/">
                <button className="flex items-center gap-1.5 text-xs text-ink-soft hover:text-foreground transition-colors">
                  <LogOut className="w-3.5 h-3.5" />
                  Switch account
                </button>
              </SignOutButton>
            </div>
          </div>
          <span className="text-sm text-ink-soft">
            Step {currentStep + 1} of {steps.length}
          </span>
        </div>
      </div>

      <div className="container-tight pt-8 pb-4">
        <div className="flex items-center justify-between mb-8">
          {steps.map((step, i) => (
            <div key={i} className="flex items-center flex-1">
              <div className="flex flex-col items-center gap-2">
                <div
                  className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all ${
                    i <= currentStep
                      ? "bg-gradient-primary text-primary-foreground shadow-glow"
                      : "bg-line text-ink-soft"
                  }`}
                >
                  {i < currentStep ? <Check className="w-5 h-5" /> : <step.icon className="w-5 h-5" />}
                </div>
                <span className={`text-xs font-medium hidden sm:block ${i <= currentStep ? "text-foreground" : "text-ink-soft"}`}>
                  {step.label}
                </span>
              </div>
              {i < steps.length - 1 && (
                <div className={`flex-1 h-px mx-3 ${i < currentStep ? "bg-primary" : "bg-border"}`} />
              )}
            </div>
          ))}
        </div>
        <Progress value={((currentStep + 1) / steps.length) * 100} className="h-1" />
      </div>

      <div className="container-tight flex-1 pb-8">
        <div className="dash-card p-8">
          <p className="eyebrow mb-2">Setup</p>
          <h2 className="font-display font-bold text-xl mb-1">{steps[currentStep].label}</h2>
          <p className="text-sm text-ink-soft mb-6">
            {currentStep === 0 && "Select your business type to customize your AI experience."}
            {currentStep === 1 && `Tell us about your ${getBusinessLabel().toLowerCase()} so we can personalize your AI.`}
            {currentStep === 2 && `${isAppointmentBusiness ? "List your services so the AI knows what to book." : "Paste your menu so the AI knows what to offer callers."}`}
            {currentStep === 3 && "Customize how your AI sounds and behaves."}
            {currentStep === 4 && "Start your 7-day free trial. No charge today."}
          </p>

          <AnimatePresence mode="wait">
            <motion.div
              key={currentStep}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
            >
              {renderStep()}
            </motion.div>
          </AnimatePresence>

          <div className="flex justify-between mt-8 pt-6 border-t border-line">
            <Button
              type="button"
              variant="ghost"
              onClick={handleBack}
              disabled={currentStep === 0 || submitting || parsing || activating}
              className="rounded-xl"
            >
              <ArrowLeft className="mr-2 w-4 h-4" />
              Back
            </Button>

            <Button
              type="button"
              onClick={handleNext}
              disabled={submitting || parsing || activating}
              className="bg-gradient-primary text-primary-foreground rounded-xl px-8 shadow-glow hover:opacity-90"
            >
              {currentStep === steps.length - 1
                ? activating ? "Redirecting to checkout..." : "Start Free Trial →"
                : submitting ? "Saving..." : "Continue"}
              {currentStep < steps.length - 1 && <ArrowRight className="ml-2 w-4 h-4" />}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
