import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  ChevronRight,
  ChevronLeft,
  UtensilsCrossed,
  FileText,
  Settings,
  Rocket,
  Check,
  PhoneCall,
} from "lucide-react";
import { toast } from "sonner";
import { motion, AnimatePresence } from "framer-motion";
import {
  activateRestaurant,
  confirmMenu,
  createRestaurant as createRestaurantApi,
  parseMenu as parseMenuApi,
  setRestaurantId as persistRestaurantId,
  updateConfig,
} from "@/lib/api";
import { useAppSession } from "@/context/AppSessionContext";

const steps = [
  { id: 1, label: "Restaurant Info", icon: UtensilsCrossed },
  { id: 2, label: "Menu Setup", icon: FileText },
  { id: 3, label: "AI Configuration", icon: Settings },
  { id: 4, label: "Go Live", icon: Rocket },
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

const days = [
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
  const { activeRestaurant, onboardingComplete, refreshSession, setActiveRestaurant } = useAppSession();

  const [step, setStep] = useState(1);
  const [restaurantId, setRestaurantId] = useState(null);

  const [restaurantData, setRestaurantData] = useState({
    name: "",
    cuisine_type: "",
    address: "",
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
    reservations_enabled: false,
    catering_enabled: false,
    avg_prep_time_minutes: 20,
    reservation_party_limit: 8,
  });

  const [menuText, setMenuText] = useState("");
  const [parsedItems, setParsedItems] = useState([]);
  const [parsing, setParsing] = useState(false);

  const [aiConfig, setAiConfig] = useState({
    persona: "friendly",
    disclosure_text: "",
    upsell_enabled: true,
    primary_language: "en",
    after_hours_mode: "voicemail",
    voicemail_enabled: true,
    escalation_phone_number: "",
    operating_hours: defaultHours,
  });

  const [activating, setActivating] = useState(false);
  const [activated, setActivated] = useState(false);

  useEffect(() => {
    if (activeRestaurant && !restaurantId) {
      setRestaurantId(activeRestaurant.id);
      setRestaurantData({
        name: activeRestaurant.name || "",
        cuisine_type: activeRestaurant.cuisine_type || "",
        address: activeRestaurant.address || "",
        timezone: activeRestaurant.timezone || "America/Chicago",

        owner_name: activeRestaurant.owner_name || "",
        owner_email: activeRestaurant.owner_email || "",
        owner_phone: activeRestaurant.owner_phone || "",
        billing_email: activeRestaurant.billing_email || "",
        business_phone: activeRestaurant.business_phone || "",
        website: activeRestaurant.website || "",
        primary_language: activeRestaurant.primary_language || "en",

        pickup_enabled: activeRestaurant.pickup_enabled ?? true,
        delivery_enabled: activeRestaurant.delivery_enabled ?? true,
        dine_in_enabled: activeRestaurant.dine_in_enabled ?? true,
        reservations_enabled: activeRestaurant.reservations_enabled ?? false,
        catering_enabled: activeRestaurant.catering_enabled ?? false,
        avg_prep_time_minutes: activeRestaurant.avg_prep_time_minutes ?? 20,
        reservation_party_limit: activeRestaurant.reservation_party_limit ?? 8,
      });

      if (activeRestaurant.is_active) {
        setActivated(true);
        setStep(4);
      }
    }
  }, [activeRestaurant, restaurantId]);

  useEffect(() => {
    if (activeRestaurant && onboardingComplete) {
      navigate("/dashboard", { replace: true });
    }
  }, [activeRestaurant, onboardingComplete, navigate]);

  const createRestaurant = async () => {
    if (!restaurantData.name.trim()) {
      toast.error("Restaurant name is required");
      return;
    }

    try {
      const res = await createRestaurantApi(restaurantData);
      const createdRestaurant = res.data;

      setRestaurantId(createdRestaurant.id);
      persistRestaurantId(createdRestaurant.id);
      setActiveRestaurant(createdRestaurant);

      setAiConfig((prev) => ({
        ...prev,
        primary_language: createdRestaurant.primary_language || "en",
        disclosure_text: `Hi! I'm an AI assistant for ${createdRestaurant.name}. How can I help you today?`,
      }));

      toast.success("Restaurant created!");
      setStep(2);
    } catch (err) {
      console.error("Create restaurant error:", err);
      toast.error(err?.response?.data?.detail || "Failed to create restaurant");
    }
  };

  const parseMenu = async () => {
    if (!menuText.trim()) {
      toast.error("Please enter your menu text");
      return;
    }

    setParsing(true);
    try {
      const res = await parseMenuApi({
        menu_text: menuText,
        restaurant_id: restaurantId,
      });
      setParsedItems(res.data.items || []);
      if (res.data.items?.length > 0) {
        toast.success(`Parsed ${res.data.items.length} menu items!`);
      } else {
        toast.warning("No items could be parsed. Try a different format.");
      }
    } catch (err) {
      console.error("Parse menu error:", err);
      toast.error(err?.response?.data?.detail || "Failed to parse menu");
    } finally {
      setParsing(false);
    }
  };

  const saveMenuAndProceed = async () => {
    if (parsedItems.length === 0) {
      toast.warning("Parse your menu first");
      return;
    }

    try {
      await confirmMenu(restaurantId, parsedItems);
      toast.success("Menu saved!");
      setStep(3);
    } catch (err) {
      console.error("Save menu error:", err);
      toast.error(err?.response?.data?.detail || "Failed to save menu");
    }
  };

  const saveConfigAndProceed = async () => {
    try {
      await updateConfig(restaurantId, aiConfig);
      toast.success("AI configuration saved!");
      setStep(4);
    } catch (err) {
      console.error("Save config error:", err);
      toast.error(err?.response?.data?.detail || "Failed to save config");
    }
  };

  const goLive = async () => {
    setActivating(true);
    try {
      await activateRestaurant(restaurantId);
      await refreshSession(restaurantId);
      setActivated(true);
      toast.success("Your AI phone agent is live!");
      setTimeout(() => navigate("/dashboard"), 700);
    } catch (err) {
      console.error("Activate error:", err);
      toast.error(err?.response?.data?.detail || "Failed to activate");
    } finally {
      setActivating(false);
    }
  };

  const updateHours = (dayKey, field, value) => {
    setAiConfig((prev) => ({
      ...prev,
      operating_hours: {
        ...prev.operating_hours,
        [dayKey]: {
          ...prev.operating_hours[dayKey],
          [field]: value,
        },
      },
    }));
  };

  const progress = (step / steps.length) * 100;

  return (
    <div className="min-h-screen bg-background">
      <div className="border-b border-border bg-card px-4 lg:px-8 py-4">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <a href="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-primary flex items-center justify-center">
              <PhoneCall className="w-4 h-4 text-primary-foreground" />
            </div>
            <span className="text-lg font-heading font-bold text-foreground">
              ring<span className="text-gradient-primary">AI</span>
            </span>
          </a>
          <Badge variant="secondary" className="text-xs">
            Setup Wizard
          </Badge>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 lg:px-8 py-8">
        <div className="mb-8">
          <div className="flex items-center justify-between mb-3">
            {steps.map((s, i) => (
              <div key={s.id} className="flex items-center gap-2">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold ${
                    step > s.id
                      ? "bg-primary text-primary-foreground"
                      : step === s.id
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground"
                  }`}
                >
                  {step > s.id ? <Check className="w-4 h-4" /> : s.id}
                </div>
                <span
                  className={`hidden sm:block text-xs font-medium ${
                    step >= s.id ? "text-foreground" : "text-muted-foreground"
                  }`}
                >
                  {s.label}
                </span>
                {i < steps.length - 1 && <div className="hidden sm:block w-8 lg:w-16 h-px bg-border" />}
              </div>
            ))}
          </div>
          <Progress value={progress} className="h-1" />
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.3 }}
          >
            {step === 1 && (
              <Card className="p-6 lg:p-8 border-border bg-card">
                <h2 className="text-xl font-heading font-bold text-foreground mb-1">
                  Tell us about your restaurant
                </h2>
                <p className="text-sm text-muted-foreground mb-6">
                  We'll use this to customize your AI phone agent and business setup.
                </p>

                <div className="space-y-5">
                  <div className="grid sm:grid-cols-2 gap-4">
                    <div>
                      <Label className="text-xs">Restaurant Name *</Label>
                      <Input
                        value={restaurantData.name}
                        onChange={(e) => setRestaurantData({ ...restaurantData, name: e.target.value })}
                        placeholder="Bella Cucina"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Cuisine Type</Label>
                      <Input
                        value={restaurantData.cuisine_type}
                        onChange={(e) => setRestaurantData({ ...restaurantData, cuisine_type: e.target.value })}
                        placeholder="Italian, Mexican, Chinese..."
                      />
                    </div>
                  </div>

                  <div className="grid sm:grid-cols-2 gap-4">
                    <div>
                      <Label className="text-xs">Owner Name</Label>
                      <Input
                        value={restaurantData.owner_name}
                        onChange={(e) => setRestaurantData({ ...restaurantData, owner_name: e.target.value })}
                        placeholder="Owner full name"
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Owner Email</Label>
                      <Input
                        type="email"
                        value={restaurantData.owner_email}
                        onChange={(e) => setRestaurantData({ ...restaurantData, owner_email: e.target.value })}
                        placeholder="owner@example.com"
                      />
                    </div>
                  </div>

                  <div className="grid sm:grid-cols-2 gap-4">
                    <div>
                      <Label className="text-xs">Owner Phone</Label>
                      <Input
                        value={restaurantData.owner_phone}
                        onChange={(e) => setRestaurantData({ ...restaurantData, owner_phone: e.target.value })}
                        placeholder="+1..."
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Billing Email</Label>
                      <Input
                        type="email"
                        value={restaurantData.billing_email}
                        onChange={(e) => setRestaurantData({ ...restaurantData, billing_email: e.target.value })}
                        placeholder="billing@example.com"
                      />
                    </div>
                  </div>

                  <div className="grid sm:grid-cols-2 gap-4">
                    <div>
                      <Label className="text-xs">Business Phone</Label>
                      <Input
                        value={restaurantData.business_phone}
                        onChange={(e) => setRestaurantData({ ...restaurantData, business_phone: e.target.value })}
                        placeholder="+1..."
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Website</Label>
                      <Input
                        value={restaurantData.website}
                        onChange={(e) => setRestaurantData({ ...restaurantData, website: e.target.value })}
                        placeholder="https://yourrestaurant.com"
                      />
                    </div>
                  </div>

                  <div>
                    <Label className="text-xs">Address</Label>
                    <Input
                      value={restaurantData.address}
                      onChange={(e) => setRestaurantData({ ...restaurantData, address: e.target.value })}
                      placeholder="123 Main St, City, State"
                    />
                  </div>

                  <div className="grid sm:grid-cols-2 gap-4">
                    <div>
                      <Label className="text-xs">Timezone</Label>
                      <Select
                        value={restaurantData.timezone}
                        onValueChange={(v) => setRestaurantData({ ...restaurantData, timezone: v })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="America/New_York">Eastern</SelectItem>
                          <SelectItem value="America/Chicago">Central</SelectItem>
                          <SelectItem value="America/Denver">Mountain</SelectItem>
                          <SelectItem value="America/Los_Angeles">Pacific</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div>
                      <Label className="text-xs">Primary Language</Label>
                      <Select
                        value={restaurantData.primary_language}
                        onValueChange={(v) => setRestaurantData({ ...restaurantData, primary_language: v })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="en">English</SelectItem>
                          <SelectItem value="es">Spanish</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="grid sm:grid-cols-2 gap-4">
                    <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                      <span className="text-sm">Pickup Enabled</span>
                      <input
                        type="checkbox"
                        checked={restaurantData.pickup_enabled}
                        onChange={(e) => setRestaurantData({ ...restaurantData, pickup_enabled: e.target.checked })}
                        className="accent-primary"
                      />
                    </div>
                    <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                      <span className="text-sm">Delivery Enabled</span>
                      <input
                        type="checkbox"
                        checked={restaurantData.delivery_enabled}
                        onChange={(e) => setRestaurantData({ ...restaurantData, delivery_enabled: e.target.checked })}
                        className="accent-primary"
                      />
                    </div>
                    <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                      <span className="text-sm">Dine-in Enabled</span>
                      <input
                        type="checkbox"
                        checked={restaurantData.dine_in_enabled}
                        onChange={(e) => setRestaurantData({ ...restaurantData, dine_in_enabled: e.target.checked })}
                        className="accent-primary"
                      />
                    </div>
                    <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                      <span className="text-sm">Reservations Enabled</span>
                      <input
                        type="checkbox"
                        checked={restaurantData.reservations_enabled}
                        onChange={(e) => setRestaurantData({ ...restaurantData, reservations_enabled: e.target.checked })}
                        className="accent-primary"
                      />
                    </div>
                  </div>

                  <div className="grid sm:grid-cols-2 gap-4">
                    <div>
                      <Label className="text-xs">Average Prep Time (minutes)</Label>
                      <Input
                        type="number"
                        value={restaurantData.avg_prep_time_minutes}
                        onChange={(e) =>
                          setRestaurantData({
                            ...restaurantData,
                            avg_prep_time_minutes: Number(e.target.value || 0),
                          })
                        }
                      />
                    </div>
                    <div>
                      <Label className="text-xs">Reservation Party Limit</Label>
                      <Input
                        type="number"
                        value={restaurantData.reservation_party_limit}
                        onChange={(e) =>
                          setRestaurantData({
                            ...restaurantData,
                            reservation_party_limit: Number(e.target.value || 0),
                          })
                        }
                      />
                    </div>
                  </div>

                  <div className="pt-2">
                    <Button variant="premium" onClick={createRestaurant} className="w-full">
                      Continue <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </Card>
            )}

            {step === 2 && (
              <Card className="p-6 lg:p-8 border-border bg-card">
                <h2 className="text-xl font-heading font-bold text-foreground mb-1">
                  Upload Your Menu
                </h2>
                <p className="text-sm text-muted-foreground mb-6">
                  Paste your menu text and our AI will parse it into structured data.
                </p>

                <div className="space-y-4">
                  <div>
                    <Label className="text-xs">Menu Text</Label>
                    <Textarea
                      value={menuText}
                      onChange={(e) => setMenuText(e.target.value)}
                      placeholder={
                        "APPETIZERS\nBruschetta - $12.99\nCalamari Fritti - $14.99\n\nPASTA\nSpaghetti Bolognese - $18.99\nFettuccine Alfredo - $17.99"
                      }
                      rows={10}
                      className="font-mono text-sm"
                    />
                  </div>

                  <Button variant="outline" onClick={parseMenu} disabled={parsing} className="w-full">
                    {parsing ? "Parsing with AI..." : "Parse Menu"}
                  </Button>

                  {parsedItems.length > 0 && (
                    <div className="border border-border rounded-lg overflow-hidden">
                      <div className="p-3 bg-muted/30">
                        <p className="text-xs font-medium text-foreground">
                          {parsedItems.length} items parsed
                        </p>
                      </div>
                      <div className="divide-y divide-border max-h-64 overflow-y-auto">
                        {parsedItems.map((item, i) => (
                          <div key={i} className="flex items-center justify-between px-4 py-2">
                            <div>
                              <p className="text-sm text-foreground">{item.name}</p>
                              <p className="text-xs text-muted-foreground">{item.category}</p>
                            </div>
                            <span className="text-sm font-medium text-foreground">
                              {item.price ? `$${(item.price / 100).toFixed(2)}` : "--"}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="flex gap-2 pt-2">
                    <Button variant="outline" onClick={() => setStep(1)}>
                      <ChevronLeft className="w-4 h-4" /> Back
                    </Button>
                    <Button
                      variant="premium"
                      onClick={saveMenuAndProceed}
                      className="flex-1"
                      disabled={parsedItems.length === 0}
                    >
                      Save & Continue <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </Card>
            )}

            {step === 3 && (
              <Card className="p-6 lg:p-8 border-border bg-card">
                <h2 className="text-xl font-heading font-bold text-foreground mb-1">
                  Configure Your AI Agent
                </h2>
                <p className="text-sm text-muted-foreground mb-6">
                  Customize how your AI phone agent sounds and behaves.
                </p>

                <div className="space-y-5">
                  <div>
                    <Label className="text-xs">Persona</Label>
                    <Select
                      value={aiConfig.persona}
                      onValueChange={(v) => setAiConfig({ ...aiConfig, persona: v })}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="friendly">Friendly & Warm</SelectItem>
                        <SelectItem value="professional">Professional & Formal</SelectItem>
                        <SelectItem value="casual">Casual & Relaxed</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label className="text-xs">Greeting Message</Label>
                    <Textarea
                      value={aiConfig.disclosure_text}
                      onChange={(e) => setAiConfig({ ...aiConfig, disclosure_text: e.target.value })}
                      rows={2}
                    />
                  </div>

                  <div className="grid sm:grid-cols-2 gap-4">
                    <div>
                      <Label className="text-xs">Primary Language</Label>
                      <Select
                        value={aiConfig.primary_language}
                        onValueChange={(v) => setAiConfig({ ...aiConfig, primary_language: v })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="en">English</SelectItem>
                          <SelectItem value="es">Spanish</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div>
                      <Label className="text-xs">After-hours Behavior</Label>
                      <Select
                        value={aiConfig.after_hours_mode}
                        onValueChange={(v) => setAiConfig({ ...aiConfig, after_hours_mode: v })}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="voicemail">Take voicemail</SelectItem>
                          <SelectItem value="close_message">Play closed message</SelectItem>
                          <SelectItem value="forward">Escalate to phone</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div>
                    <Label className="text-xs">Escalation Phone Number</Label>
                    <Input
                      value={aiConfig.escalation_phone_number}
                      onChange={(e) => setAiConfig({ ...aiConfig, escalation_phone_number: e.target.value })}
                      placeholder="+1..."
                    />
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                    <div>
                      <p className="text-sm font-medium text-foreground">Enable Upselling</p>
                      <p className="text-xs text-muted-foreground">AI suggests add-ons and sides</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={aiConfig.upsell_enabled}
                      onChange={(e) => setAiConfig({ ...aiConfig, upsell_enabled: e.target.checked })}
                      className="accent-primary"
                    />
                  </div>

                  <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                    <div>
                      <p className="text-sm font-medium text-foreground">Voicemail Enabled</p>
                      <p className="text-xs text-muted-foreground">Allow voicemail after hours</p>
                    </div>
                    <input
                      type="checkbox"
                      checked={aiConfig.voicemail_enabled}
                      onChange={(e) => setAiConfig({ ...aiConfig, voicemail_enabled: e.target.checked })}
                      className="accent-primary"
                    />
                  </div>

                  <div>
                    <Label className="text-xs mb-3 block">Operating Hours</Label>
                    <div className="space-y-3">
                      {days.map(([key, label]) => {
                        const day = aiConfig.operating_hours[key];
                        return (
                          <div key={key} className="grid grid-cols-12 gap-2 items-center p-3 rounded-lg bg-muted/20">
                            <div className="col-span-3">
                              <p className="text-sm font-medium text-foreground">{label}</p>
                            </div>
                            <div className="col-span-2 flex items-center gap-2">
                              <input
                                type="checkbox"
                                checked={day.closed}
                                onChange={(e) => updateHours(key, "closed", e.target.checked)}
                                className="accent-primary"
                              />
                              <span className="text-xs text-muted-foreground">Closed</span>
                            </div>
                            <div className="col-span-3">
                              <Input
                                type="time"
                                value={day.open}
                                disabled={day.closed}
                                onChange={(e) => updateHours(key, "open", e.target.value)}
                              />
                            </div>
                            <div className="col-span-1 text-center text-xs text-muted-foreground">to</div>
                            <div className="col-span-3">
                              <Input
                                type="time"
                                value={day.close}
                                disabled={day.closed}
                                onChange={(e) => updateHours(key, "close", e.target.value)}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div className="flex gap-2 pt-2">
                    <Button variant="outline" onClick={() => setStep(2)}>
                      <ChevronLeft className="w-4 h-4" /> Back
                    </Button>
                    <Button variant="premium" onClick={saveConfigAndProceed} className="flex-1">
                      Save & Continue <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </Card>
            )}

            {step === 4 && (
              <Card className="p-6 lg:p-8 border-border bg-card text-center">
                {!activated ? (
                  <>
                    <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
                      <Rocket className="w-8 h-8 text-primary" />
                    </div>
                    <h2 className="text-xl font-heading font-bold text-foreground mb-2">
                      Ready to Go Live!
                    </h2>
                    <p className="text-sm text-muted-foreground mb-6">
                      Your AI phone agent is configured and ready. Activating will mark your restaurant active.
                      Provision a Twilio number and complete billing from Settings.
                    </p>
                    <div className="flex flex-col gap-2">
                      <Button variant="premium" size="lg" onClick={goLive} disabled={activating} className="w-full">
                        {activating ? "Activating..." : "Activate AI Phone Agent"}
                      </Button>
                      <Button variant="outline" onClick={() => setStep(3)}>
                        <ChevronLeft className="w-4 h-4" /> Back to Config
                      </Button>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="w-16 h-16 rounded-2xl bg-success/10 flex items-center justify-center mx-auto mb-4">
                      <Check className="w-8 h-8 text-success" />
                    </div>
                    <h2 className="text-xl font-heading font-bold text-foreground mb-2">
                      You're Live!
                    </h2>
                    <p className="text-sm text-muted-foreground mb-6">
                      Your restaurant is active. Next, connect billing and provision your Twilio number from Settings.
                    </p>
                    <Button variant="premium" size="lg" onClick={() => navigate("/dashboard")} className="w-full">
                      Go to Dashboard <ChevronRight className="w-4 h-4" />
                    </Button>
                  </>
                )}
              </Card>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}