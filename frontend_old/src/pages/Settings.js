import { useState, useEffect, useCallback } from "react";
import { AppLayout } from "@/layouts/AppLayout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Settings as SettingsIcon,
  Mic,
  ShieldAlert,
  CreditCard,
  Plus,
  X,
  Save,
  Volume2,
  AlertTriangle,
  TestTube,
  CheckCircle2,
  XCircle,
  Sparkles,
  Phone,
  Key,
} from "lucide-react";
import {
  createBillingCheckout,
  getRestaurant,
  getRestaurantId,
  getConfig,
  getSquareConnectUrl,
  getTestModeStatus,
  getTwilioStatus,
  provisionTwilioNumber,
  updateConfig,
  updateRestaurant,
} from "@/lib/api";
import { useAppSession } from "@/context/AppSessionContext";
import { toast } from "sonner";

const voiceOptions = [
  { id: "21m00Tcm4TlvDq8ikWAM", name: "Rachel - Professional", accent: "American" },
  { id: "AZnzlk1XvdvUeBnXmlld", name: "Domi - Warm", accent: "American" },
  { id: "EXAVITQu4vr4xnSDxMaL", name: "Bella - Friendly", accent: "American" },
  { id: "TX3LPaxmHKxFdv7VOQHJ", name: "Liam - Calm", accent: "American" },
  { id: "onwK4e9ZLuTAKqWW03F9", name: "Daniel - Authoritative", accent: "British" },
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

export default function Settings() {
  const { activeRestaurant, refreshSession } = useAppSession();

  const [restaurant, setRestaurant] = useState(null);
  const [config, setConfig] = useState(null);
  const [testMode, setTestMode] = useState(null);
  const [twilioStatus, setTwilioStatus] = useState(null);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [newRule, setNewRule] = useState("");
  const [newEscalation, setNewEscalation] = useState("");
  const [areaCode, setAreaCode] = useState("");

  const fetchData = useCallback(async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      if (!restaurantId) {
        toast.error("No active restaurant selected");
        setLoading(false);
        return;
      }

      const [restRes, configRes, testModeRes, twilioRes] = await Promise.all([
        getRestaurant(restaurantId),
        getConfig(restaurantId),
        getTestModeStatus(),
        getTwilioStatus(restaurantId),
      ]);

      setRestaurant(restRes.data);
      setConfig({
        operating_hours: defaultHours,
        ...configRes.data,
        operating_hours: {
          ...defaultHours,
          ...(configRes.data?.operating_hours || {}),
        },
      });
      setTestMode(testModeRes.data);
      setTwilioStatus(twilioRes.data);
    } catch (err) {
      console.error("Settings load error:", err);
      toast.error("Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, [activeRestaurant]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const saveRestaurant = async () => {
    setSaving(true);
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      await updateRestaurant(restaurantId, {
        name: restaurant?.name,
        cuisine_type: restaurant?.cuisine_type,
        address: restaurant?.address,
        timezone: restaurant?.timezone,
        owner_name: restaurant?.owner_name,
        owner_email: restaurant?.owner_email,
        owner_phone: restaurant?.owner_phone,
        billing_email: restaurant?.billing_email,
        business_phone: restaurant?.business_phone,
        website: restaurant?.website,
        primary_language: restaurant?.primary_language,
        pickup_enabled: restaurant?.pickup_enabled,
        delivery_enabled: restaurant?.delivery_enabled,
        dine_in_enabled: restaurant?.dine_in_enabled,
        reservations_enabled: restaurant?.reservations_enabled,
        catering_enabled: restaurant?.catering_enabled,
        avg_prep_time_minutes: Number(restaurant?.avg_prep_time_minutes || 0),
        reservation_party_limit: Number(restaurant?.reservation_party_limit || 0),
      });
      await refreshSession(restaurantId);
      await fetchData();
      toast.success("Restaurant info saved!");
    } catch (err) {
      console.error("Save restaurant error:", err);
      toast.error(err?.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const saveConfig = async () => {
    setSaving(true);
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      await updateConfig(restaurantId, {
        persona: config?.persona,
        voice_id: config?.voice_id,
        primary_language: config?.primary_language,
        business_rules: config?.business_rules,
        escalation_rules: config?.escalation_rules,
        upsell_enabled: config?.upsell_enabled,
        disclosure_text: config?.disclosure_text,
        delivery_enabled: config?.delivery_enabled,
        delivery_minimum: Number(config?.delivery_minimum || 0),
        after_hours_mode: config?.after_hours_mode,
        voicemail_enabled: config?.voicemail_enabled,
        escalation_phone_number: config?.escalation_phone_number,
        operating_hours: config?.operating_hours,
      });
      await refreshSession(restaurantId);
      await fetchData();
      toast.success("AI configuration saved!");
    } catch (err) {
      console.error("Save config error:", err);
      toast.error(err?.response?.data?.detail || "Failed to save config");
    } finally {
      setSaving(false);
    }
  };

  const connectSquare = async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const res = await getSquareConnectUrl(restaurantId);
      const url = res?.data?.connect_url;

      if (!url) {
        toast.error("Square connect URL not available");
        return;
      }

      window.location.href = url;
    } catch (err) {
      console.error("Square connect error:", err);
      toast.error(err?.response?.data?.detail || "Failed to start Square connection");
    }
  };

  const manageBilling = async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const res = await createBillingCheckout({ restaurant_id: restaurantId });
      const url = res?.data?.checkout_url;

      if (!url) {
        toast.error("Billing checkout URL not available");
        return;
      }

      window.location.href = url;
    } catch (err) {
      console.error("Billing error:", err);
      toast.error(err?.response?.data?.detail || "Failed to open billing");
    }
  };

  const provisionNumber = async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      await provisionTwilioNumber(restaurantId, areaCode);
      await fetchData();
      toast.success("Twilio number provisioned");
    } catch (err) {
      console.error("Provision Twilio number error:", err);
      toast.error(err?.response?.data?.detail || "Failed to provision Twilio number");
    }
  };

  const addRule = () => {
    if (!newRule.trim()) return;
    setConfig((prev) => ({
      ...prev,
      business_rules: [...(prev.business_rules || []), newRule.trim()],
    }));
    setNewRule("");
  };

  const removeRule = (i) => {
    setConfig((prev) => ({
      ...prev,
      business_rules: prev.business_rules.filter((_, idx) => idx !== i),
    }));
  };

  const addEscalation = () => {
    if (!newEscalation.trim()) return;
    setConfig((prev) => ({
      ...prev,
      escalation_rules: [...(prev.escalation_rules || []), newEscalation.trim()],
    }));
    setNewEscalation("");
  };

  const removeEscalation = (i) => {
    setConfig((prev) => ({
      ...prev,
      escalation_rules: prev.escalation_rules.filter((_, idx) => idx !== i),
    }));
  };

  const updateHours = (dayKey, field, value) => {
    setConfig((prev) => ({
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

  if (loading) {
    return (
      <AppLayout>
        <div className="p-6">
          <div className="space-y-4">
            {[...Array(3)].map((_, i) => (
              <Card key={i} className="p-6 animate-pulse border-border bg-card">
                <div className="h-40 bg-muted rounded" />
              </Card>
            ))}
          </div>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="p-4 lg:p-6 space-y-4">
        <div>
          <h1 className="text-2xl font-heading font-bold text-foreground">Settings</h1>
          <p className="text-sm text-muted-foreground">Configure your AI phone agent</p>
        </div>

        <Tabs defaultValue="general" className="w-full">
          <TabsList className="grid w-full max-w-xl grid-cols-5">
            <TabsTrigger value="general" className="text-xs">General</TabsTrigger>
            <TabsTrigger value="voice" className="text-xs">Voice & AI</TabsTrigger>
            <TabsTrigger value="rules" className="text-xs">Rules</TabsTrigger>
            <TabsTrigger value="integrations" className="text-xs">Integrations</TabsTrigger>
            <TabsTrigger value="billing" className="text-xs">Billing</TabsTrigger>
          </TabsList>

          <TabsContent value="general" className="mt-4">
            <Card className="p-6 border-border bg-card">
              <h3 className="text-base font-heading font-semibold text-foreground mb-4 flex items-center gap-2">
                <SettingsIcon className="w-4 h-4" /> Restaurant Information
              </h3>

              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <Label className="text-xs">Restaurant Name</Label>
                  <Input
                    value={restaurant?.name || ""}
                    onChange={(e) => setRestaurant({ ...restaurant, name: e.target.value })}
                  />
                </div>
                <div>
                  <Label className="text-xs">Cuisine Type</Label>
                  <Input
                    value={restaurant?.cuisine_type || ""}
                    onChange={(e) => setRestaurant({ ...restaurant, cuisine_type: e.target.value })}
                  />
                </div>

                <div>
                  <Label className="text-xs">Owner Name</Label>
                  <Input
                    value={restaurant?.owner_name || ""}
                    onChange={(e) => setRestaurant({ ...restaurant, owner_name: e.target.value })}
                  />
                </div>
                <div>
                  <Label className="text-xs">Owner Email</Label>
                  <Input
                    value={restaurant?.owner_email || ""}
                    onChange={(e) => setRestaurant({ ...restaurant, owner_email: e.target.value })}
                  />
                </div>

                <div>
                  <Label className="text-xs">Owner Phone</Label>
                  <Input
                    value={restaurant?.owner_phone || ""}
                    onChange={(e) => setRestaurant({ ...restaurant, owner_phone: e.target.value })}
                  />
                </div>
                <div>
                  <Label className="text-xs">Billing Email</Label>
                  <Input
                    value={restaurant?.billing_email || ""}
                    onChange={(e) => setRestaurant({ ...restaurant, billing_email: e.target.value })}
                  />
                </div>

                <div>
                  <Label className="text-xs">Business Phone</Label>
                  <Input
                    value={restaurant?.business_phone || ""}
                    onChange={(e) => setRestaurant({ ...restaurant, business_phone: e.target.value })}
                  />
                </div>
                <div>
                  <Label className="text-xs">Website</Label>
                  <Input
                    value={restaurant?.website || ""}
                    onChange={(e) => setRestaurant({ ...restaurant, website: e.target.value })}
                  />
                </div>

                <div className="sm:col-span-2">
                  <Label className="text-xs">Address</Label>
                  <Input
                    value={restaurant?.address || ""}
                    onChange={(e) => setRestaurant({ ...restaurant, address: e.target.value })}
                  />
                </div>

                <div>
                  <Label className="text-xs">Timezone</Label>
                  <Select
                    value={restaurant?.timezone || "America/Chicago"}
                    onValueChange={(v) => setRestaurant({ ...restaurant, timezone: v })}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
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
                    value={restaurant?.primary_language || "en"}
                    onValueChange={(v) => setRestaurant({ ...restaurant, primary_language: v })}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="en">English</SelectItem>
                      <SelectItem value="es">Spanish</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label className="text-xs">Phone Number</Label>
                  <Input
                    value={restaurant?.phone_number || ""}
                    placeholder="No phone number assigned yet"
                    readOnly
                  />
                </div>

                <div>
                  <Label className="text-xs">Average Prep Time (minutes)</Label>
                  <Input
                    type="number"
                    value={restaurant?.avg_prep_time_minutes ?? 20}
                    onChange={(e) =>
                      setRestaurant({
                        ...restaurant,
                        avg_prep_time_minutes: Number(e.target.value || 0),
                      })
                    }
                  />
                </div>

                <div>
                  <Label className="text-xs">Reservation Party Limit</Label>
                  <Input
                    type="number"
                    value={restaurant?.reservation_party_limit ?? 8}
                    onChange={(e) =>
                      setRestaurant({
                        ...restaurant,
                        reservation_party_limit: Number(e.target.value || 0),
                      })
                    }
                  />
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                  <div>
                    <p className="text-sm font-medium text-foreground">Pickup Enabled</p>
                  </div>
                  <Switch
                    checked={restaurant?.pickup_enabled ?? true}
                    onCheckedChange={(v) => setRestaurant({ ...restaurant, pickup_enabled: v })}
                  />
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                  <div>
                    <p className="text-sm font-medium text-foreground">Delivery Enabled</p>
                  </div>
                  <Switch
                    checked={restaurant?.delivery_enabled ?? true}
                    onCheckedChange={(v) => setRestaurant({ ...restaurant, delivery_enabled: v })}
                  />
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                  <div>
                    <p className="text-sm font-medium text-foreground">Dine-in Enabled</p>
                  </div>
                  <Switch
                    checked={restaurant?.dine_in_enabled ?? true}
                    onCheckedChange={(v) => setRestaurant({ ...restaurant, dine_in_enabled: v })}
                  />
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                  <div>
                    <p className="text-sm font-medium text-foreground">Reservations Enabled</p>
                  </div>
                  <Switch
                    checked={restaurant?.reservations_enabled ?? false}
                    onCheckedChange={(v) => setRestaurant({ ...restaurant, reservations_enabled: v })}
                  />
                </div>

                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30 sm:col-span-2">
                  <div>
                    <p className="text-sm font-medium text-foreground">Catering Enabled</p>
                  </div>
                  <Switch
                    checked={restaurant?.catering_enabled ?? false}
                    onCheckedChange={(v) => setRestaurant({ ...restaurant, catering_enabled: v })}
                  />
                </div>
              </div>

              <div className="mt-4">
                <Button variant="premium" size="sm" onClick={saveRestaurant} disabled={saving}>
                  <Save className="w-4 h-4" /> {saving ? "Saving..." : "Save Changes"}
                </Button>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="voice" className="mt-4 space-y-4">
            <Card className="p-6 border-border bg-card">
              <h3 className="text-base font-heading font-semibold text-foreground mb-4 flex items-center gap-2">
                <Mic className="w-4 h-4" /> Voice & Persona
              </h3>

              <div className="space-y-4">
                <div>
                  <Label className="text-xs">AI Persona</Label>
                  <Select
                    value={config?.persona || "friendly"}
                    onValueChange={(v) => setConfig({ ...config, persona: v })}
                  >
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="friendly">Friendly & Warm</SelectItem>
                      <SelectItem value="professional">Professional & Formal</SelectItem>
                      <SelectItem value="casual">Casual & Relaxed</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label className="text-xs">Voice</Label>
                  <div className="grid gap-2 mt-1">
                    {voiceOptions.map((voice) => (
                      <div
                        key={voice.id}
                        onClick={() => setConfig({ ...config, voice_id: voice.id })}
                        className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                          config?.voice_id === voice.id
                            ? "border-primary bg-primary/5"
                            : "border-border hover:border-primary/30"
                        }`}
                      >
                        <Volume2 className="w-4 h-4 text-muted-foreground" />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-foreground">{voice.name}</p>
                          <p className="text-xs text-muted-foreground">{voice.accent}</p>
                        </div>
                        {config?.voice_id === voice.id && (
                          <Badge variant="secondary" className="bg-primary/10 text-primary border-0 text-xs">
                            Selected
                          </Badge>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <Label className="text-xs">Greeting Message</Label>
                  <Textarea
                    value={config?.disclosure_text || ""}
                    onChange={(e) => setConfig({ ...config, disclosure_text: e.target.value })}
                    rows={2}
                    placeholder="Hi! I'm an AI assistant..."
                  />
                </div>

                <div className="grid sm:grid-cols-2 gap-4">
                  <div>
                    <Label className="text-xs">Primary Language</Label>
                    <Select
                      value={config?.primary_language || "en"}
                      onValueChange={(v) => setConfig({ ...config, primary_language: v })}
                    >
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="en">English</SelectItem>
                        <SelectItem value="es">Spanish</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label className="text-xs">After-hours Behavior</Label>
                    <Select
                      value={config?.after_hours_mode || "voicemail"}
                      onValueChange={(v) => setConfig({ ...config, after_hours_mode: v })}
                    >
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="voicemail">Take voicemail</SelectItem>
                        <SelectItem value="close_message">Play closed message</SelectItem>
                        <SelectItem value="forward">Forward to escalation number</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div>
                  <Label className="text-xs">Escalation Phone Number</Label>
                  <Input
                    value={config?.escalation_phone_number || ""}
                    onChange={(e) => setConfig({ ...config, escalation_phone_number: e.target.value })}
                    placeholder="+1..."
                  />
                </div>

                <div>
                  <Label className="text-xs">Delivery Minimum (cents)</Label>
                  <Input
                    type="number"
                    value={config?.delivery_minimum ?? 1500}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        delivery_minimum: Number(e.target.value || 0),
                      })
                    }
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-foreground">Upselling</p>
                    <p className="text-xs text-muted-foreground">Suggest add-ons after main order</p>
                  </div>
                  <Switch
                    checked={config?.upsell_enabled || false}
                    onCheckedChange={(v) => setConfig({ ...config, upsell_enabled: v })}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-foreground">Delivery Orders</p>
                    <p className="text-xs text-muted-foreground">Accept delivery orders via phone</p>
                  </div>
                  <Switch
                    checked={config?.delivery_enabled || false}
                    onCheckedChange={(v) => setConfig({ ...config, delivery_enabled: v })}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-foreground">Voicemail Enabled</p>
                    <p className="text-xs text-muted-foreground">Allow voicemail after hours</p>
                  </div>
                  <Switch
                    checked={config?.voicemail_enabled || false}
                    onCheckedChange={(v) => setConfig({ ...config, voicemail_enabled: v })}
                  />
                </div>

                <div>
                  <Label className="text-xs mb-3 block">Operating Hours</Label>
                  <div className="space-y-3">
                    {days.map(([key, label]) => {
                      const day = config?.operating_hours?.[key] || defaultHours[key];
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

                <Button variant="premium" size="sm" onClick={saveConfig} disabled={saving}>
                  <Save className="w-4 h-4" /> {saving ? "Saving..." : "Save Config"}
                </Button>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="rules" className="mt-4 space-y-4">
            <Card className="p-6 border-border bg-card">
              <h3 className="text-base font-heading font-semibold text-foreground mb-4">
                Business Rules
              </h3>
              <p className="text-xs text-muted-foreground mb-4">
                Rules the AI will follow when handling calls
              </p>

              <div className="space-y-2 mb-4">
                {(config?.business_rules || []).map((rule, i) => (
                  <div key={i} className="flex items-center gap-2 p-2.5 rounded-lg bg-muted/30">
                    <span className="text-xs text-muted-foreground w-5 flex-shrink-0">{i + 1}.</span>
                    <span className="text-sm text-foreground flex-1">{rule}</span>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => removeRule(i)}>
                      <X className="w-3 h-3" />
                    </Button>
                  </div>
                ))}
              </div>

              <div className="flex gap-2">
                <Input
                  value={newRule}
                  onChange={(e) => setNewRule(e.target.value)}
                  placeholder="Add a business rule..."
                  onKeyDown={(e) => e.key === "Enter" && addRule()}
                />
                <Button variant="outline" size="sm" onClick={addRule}>
                  <Plus className="w-4 h-4" />
                </Button>
              </div>
            </Card>

            <Card className="p-6 border-border bg-card">
              <h3 className="text-base font-heading font-semibold text-foreground mb-4 flex items-center gap-2">
                <ShieldAlert className="w-4 h-4" /> Escalation Triggers
              </h3>
              <p className="text-xs text-muted-foreground mb-4">
                Situations where AI should transfer to a human
              </p>

              <div className="space-y-2 mb-4">
                {(config?.escalation_rules || []).map((rule, i) => (
                  <div key={i} className="flex items-center gap-2 p-2.5 rounded-lg bg-accent/5">
                    <AlertTriangle className="w-3.5 h-3.5 text-accent flex-shrink-0" />
                    <span className="text-sm text-foreground flex-1">{rule}</span>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => removeEscalation(i)}>
                      <X className="w-3 h-3" />
                    </Button>
                  </div>
                ))}
              </div>

              <div className="flex gap-2">
                <Input
                  value={newEscalation}
                  onChange={(e) => setNewEscalation(e.target.value)}
                  placeholder="Add escalation trigger..."
                  onKeyDown={(e) => e.key === "Enter" && addEscalation()}
                />
                <Button variant="outline" size="sm" onClick={addEscalation}>
                  <Plus className="w-4 h-4" />
                </Button>
              </div>
            </Card>

            <Button variant="premium" size="sm" onClick={saveConfig} disabled={saving}>
              <Save className="w-4 h-4" /> {saving ? "Saving..." : "Save All Rules"}
            </Button>
          </TabsContent>

          <TabsContent value="integrations" className="mt-4 space-y-4">
            <Card className="p-6 border-border bg-card">
              <h3 className="text-base font-heading font-semibold text-foreground mb-4 flex items-center gap-2">
                <Key className="w-4 h-4" /> Integration Status
              </h3>

              <p className="text-xs text-muted-foreground mb-4">
                Current mode:
                <Badge
                  variant="secondary"
                  className={`ml-1 ${
                    testMode?.mode === "sandbox"
                      ? "bg-primary/10 text-primary"
                      : testMode?.mode === "live"
                      ? "bg-success/10 text-success"
                      : "bg-muted"
                  } border-0`}
                >
                  {testMode?.mode || "simulation"}
                </Badge>
              </p>

              <div className="space-y-3">
                <div className="flex items-center justify-between p-4 rounded-lg border border-border">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        testMode?.integrations?.gemini?.configured ? "bg-success/10" : "bg-muted"
                      }`}
                    >
                      <Sparkles
                        className={`w-5 h-5 ${
                          testMode?.integrations?.gemini?.configured ? "text-success" : "text-muted-foreground"
                        }`}
                      />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">Gemini AI</p>
                      <p className="text-xs text-muted-foreground">
                        {testMode?.integrations?.gemini?.message || "Not configured"}
                      </p>
                    </div>
                  </div>
                  {testMode?.integrations?.gemini?.configured ? (
                    <Badge variant="secondary" className="bg-success/10 text-success border-0 gap-1">
                      <CheckCircle2 className="w-3 h-3" /> Active
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="bg-muted gap-1">
                      <XCircle className="w-3 h-3" /> Not Set
                    </Badge>
                  )}
                </div>

                <div className="flex items-center justify-between p-4 rounded-lg border border-border">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        testMode?.integrations?.twilio?.configured ? "bg-success/10" : "bg-muted"
                      }`}
                    >
                      <Phone
                        className={`w-5 h-5 ${
                          testMode?.integrations?.twilio?.configured ? "text-success" : "text-muted-foreground"
                        }`}
                      />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">Twilio Telephony</p>
                      <p className="text-xs text-muted-foreground">
                        {testMode?.integrations?.twilio?.message || "Not configured"}
                      </p>
                    </div>
                  </div>
                  {testMode?.integrations?.twilio?.configured ? (
                    <Badge variant="secondary" className="bg-success/10 text-success border-0 gap-1">
                      <CheckCircle2 className="w-3 h-3" /> Active
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="bg-accent/10 text-accent border-0 gap-1">
                      <TestTube className="w-3 h-3" /> Simulated
                    </Badge>
                  )}
                </div>

                <div className="flex items-center justify-between p-4 rounded-lg border border-border">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        testMode?.integrations?.stripe?.configured ? "bg-success/10" : "bg-muted"
                      }`}
                    >
                      <CreditCard
                        className={`w-5 h-5 ${
                          testMode?.integrations?.stripe?.configured ? "text-success" : "text-muted-foreground"
                        }`}
                      />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">Stripe Billing</p>
                      <p className="text-xs text-muted-foreground">
                        {testMode?.integrations?.stripe?.message || "Not configured"}
                      </p>
                    </div>
                  </div>
                  {testMode?.integrations?.stripe?.configured ? (
                    <Badge variant="secondary" className="bg-success/10 text-success border-0 gap-1">
                      <CheckCircle2 className="w-3 h-3" /> Active
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="bg-accent/10 text-accent border-0 gap-1">
                      <TestTube className="w-3 h-3" /> Simulated
                    </Badge>
                  )}
                </div>

                <div className="flex items-center justify-between p-4 rounded-lg border border-border">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        testMode?.integrations?.clerk?.configured ? "bg-success/10" : "bg-muted"
                      }`}
                    >
                      <ShieldAlert
                        className={`w-5 h-5 ${
                          testMode?.integrations?.clerk?.configured ? "text-success" : "text-muted-foreground"
                        }`}
                      />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">Clerk Authentication</p>
                      <p className="text-xs text-muted-foreground">
                        {testMode?.integrations?.clerk?.message || "Not configured"}
                      </p>
                    </div>
                  </div>
                  {testMode?.integrations?.clerk?.configured ? (
                    <Badge variant="secondary" className="bg-success/10 text-success border-0 gap-1">
                      <CheckCircle2 className="w-3 h-3" /> Active
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="bg-accent/10 text-accent border-0 gap-1">
                      <TestTube className="w-3 h-3" /> Demo Mode
                    </Badge>
                  )}
                </div>
              </div>
            </Card>

            <Card className="p-6 border-border bg-card">
              <h3 className="text-base font-heading font-semibold text-foreground mb-4">Twilio Number</h3>
              <div className="space-y-3">
                <div>
                  <Label className="text-xs">Current Number</Label>
                  <Input
                    value={twilioStatus?.phone_number || ""}
                    placeholder="No number assigned yet"
                    readOnly
                  />
                </div>
                <div>
                  <Label className="text-xs">Preferred Area Code</Label>
                  <Input
                    value={areaCode}
                    onChange={(e) => setAreaCode(e.target.value)}
                    placeholder="815"
                  />
                </div>
                <div className="flex gap-2 flex-wrap">
                  <Button variant="premium" size="sm" onClick={provisionNumber}>
                    Provision Twilio Number
                  </Button>
                  <Button variant="outline" size="sm" onClick={connectSquare}>
                    Connect Square
                  </Button>
                </div>
              </div>
            </Card>

            <Card className="p-6 border-border bg-card">
              <h3 className="text-base font-heading font-semibold text-foreground mb-2">Required API Keys</h3>
              <p className="text-xs text-muted-foreground mb-4">
                Add these environment variables to enable live features:
              </p>
              <div className="space-y-2 text-xs font-mono bg-muted/30 p-4 rounded-lg">
                <p className="text-muted-foreground"># Twilio (for live phone calls)</p>
                <p className="text-foreground">TWILIO_ACCOUNT_SID=ACxxxxxx</p>
                <p className="text-foreground">TWILIO_AUTH_TOKEN=xxxxxx</p>
                <p className="text-foreground">BACKEND_PUBLIC_URL=https://your-backend-url</p>

                <p className="text-muted-foreground mt-3"># Stripe (for billing)</p>
                <p className="text-foreground">STRIPE_SECRET_KEY=sk_test_xxxxx</p>
                <p className="text-foreground">STRIPE_WEBHOOK_SECRET=whsec_xxxxx</p>
                <p className="text-foreground">STRIPE_DEFAULT_PRICE_ID=price_xxxxx</p>

                <p className="text-muted-foreground mt-3"># Clerk (for authentication)</p>
                <p className="text-foreground">CLERK_PUBLISHABLE_KEY=pk_test_xxxxx</p>
                <p className="text-foreground">CLERK_SECRET_KEY=sk_test_xxxxx</p>
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="billing" className="mt-4">
            <Card className="p-6 border-border bg-card">
              <h3 className="text-base font-heading font-semibold text-foreground mb-4 flex items-center gap-2">
                <CreditCard className="w-4 h-4" /> Billing & Plan
              </h3>

              <div className="flex items-center gap-4 p-4 rounded-lg bg-primary/5 border border-primary/20 mb-6">
                <div className="flex-1">
                  <p className="text-sm font-heading font-semibold text-foreground">
                    {restaurant?.plan || "No plan assigned"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Billing status will appear here once Stripe is fully connected.
                  </p>
                </div>
                <Badge variant="secondary" className="border-0">
                  {restaurant?.billing_status || "Not configured"}
                </Badge>
              </div>

              <div className="grid sm:grid-cols-3 gap-4">
                <div className="p-4 rounded-lg bg-muted/30">
                  <p className="text-xs text-muted-foreground">Monthly Calls</p>
                  <p className="text-lg font-heading font-bold text-foreground">
                    {restaurant?.monthly_call_count || 0}
                  </p>
                </div>
                <div className="p-4 rounded-lg bg-muted/30">
                  <p className="text-xs text-muted-foreground">Billing Status</p>
                  <p className="text-lg font-heading font-bold text-foreground">
                    {restaurant?.billing_status || "--"}
                  </p>
                </div>
                <div className="p-4 rounded-lg bg-muted/30">
                  <p className="text-xs text-muted-foreground">Next Billing</p>
                  <p className="text-lg font-heading font-bold text-foreground">--</p>
                </div>
              </div>

              <Separator className="my-6" />

              <Button variant="outline" size="sm" onClick={manageBilling}>
                Manage Subscription
              </Button>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
}