import { useCallback, useEffect, useState } from "react";
import { useAppSession } from "@/context/AppSessionContext";
import { getConfig, getRestaurant, getRestaurantId, updateConfig, updateRestaurant, getVoicePreview } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AlertTriangle, Mic, Plus, Save, Settings as SettingsIcon, ShieldAlert, Volume2, X } from "lucide-react";
import { toast } from "sonner";

const voiceOptions = [
  { id: "Leda",   name: "Leda - Warm",          accent: "American" },
  { id: "Kore",   name: "Kore - Professional",   accent: "American" },
  { id: "Aoede",  name: "Aoede - Friendly",       accent: "American" },
  { id: "Puck",   name: "Puck - Energetic",       accent: "American" },
  { id: "Zephyr", name: "Zephyr - Bright",        accent: "American" },
  { id: "Orus",   name: "Orus - Confident",       accent: "American" },
  { id: "Fenrir", name: "Fenrir - Calm",          accent: "American" },
  { id: "Charon", name: "Charon - Deep",          accent: "American" },
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
const days: [keyof typeof defaultHours, string][] = [["monday","Monday"],["tuesday","Tuesday"],["wednesday","Wednesday"],["thursday","Thursday"],["friday","Friday"],["saturday","Saturday"],["sunday","Sunday"]];

// Business type helpers
const APPOINTMENT_TYPES = ["clinic", "salon", "home_services", "legal"];

const getBusinessLabel = (businessType: string) => {
  switch (businessType) {
    case "clinic": return "Clinic";
    case "salon": return "Salon";
    case "home_services": return "Business";
    case "legal": return "Office";
    default: return "Restaurant";
  }
};

const getSpecialtyLabel = (businessType: string) => {
  switch (businessType) {
    case "clinic": return "Specialty / Focus Area";
    case "salon": return "Specialty";
    case "home_services": return "Service Type";
    case "legal": return "Practice Area";
    default: return "Cuisine Type";
  }
};

const SettingsPage = () => {
  const playVoicePreview = async (voiceId: string) => {
    try {
      const res = await getVoicePreview(voiceId);
      const base64 = res.data.audio_base64;

      // Decode base64 → raw PCM bytes (Gemini returns 16-bit PCM @ 24kHz, no WAV header)
      const binaryStr = atob(base64);
      const pcmBytes = new Uint8Array(binaryStr.length);
      for (let i = 0; i < binaryStr.length; i++) pcmBytes[i] = binaryStr.charCodeAt(i);

      // Build a valid WAV container around the raw PCM
      const sampleRate = 24000;
      const numChannels = 1;
      const bitsPerSample = 16;
      const dataSize = pcmBytes.byteLength;
      const wavBuffer = new ArrayBuffer(44 + dataSize);
      const v = new DataView(wavBuffer);

      // RIFF header
      [0x52,0x49,0x46,0x46].forEach((b, i) => v.setUint8(i, b));       // "RIFF"
      v.setUint32(4, 36 + dataSize, true);
      [0x57,0x41,0x56,0x45].forEach((b, i) => v.setUint8(8 + i, b));   // "WAVE"
      // fmt chunk
      [0x66,0x6d,0x74,0x20].forEach((b, i) => v.setUint8(12 + i, b));  // "fmt "
      v.setUint32(16, 16, true);
      v.setUint16(20, 1, true);                                          // PCM
      v.setUint16(22, numChannels, true);
      v.setUint32(24, sampleRate, true);
      v.setUint32(28, sampleRate * numChannels * bitsPerSample / 8, true);
      v.setUint16(32, numChannels * bitsPerSample / 8, true);
      v.setUint16(34, bitsPerSample, true);
      // data chunk
      [0x64,0x61,0x74,0x61].forEach((b, i) => v.setUint8(36 + i, b));  // "data"
      v.setUint32(40, dataSize, true);
      new Uint8Array(wavBuffer, 44).set(pcmBytes);

      const blob = new Blob([wavBuffer], { type: "audio/wav" });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch {
      toast.error("Could not load voice preview");
    }
  };
  const { activeRestaurant, refreshSession } = useAppSession();
  const [restaurant, setRestaurant] = useState<any>(null);
  const [config, setConfig] = useState<any>(null);
  const [businessType, setBusinessType] = useState<string>("restaurant");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newRule, setNewRule] = useState("");
  const [newEscalation, setNewEscalation] = useState("");

  const isAppointmentBusiness = APPOINTMENT_TYPES.includes(businessType);

  const fetchData = useCallback(async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const [restRes, configRes] = await Promise.all([getRestaurant(restaurantId), getConfig(restaurantId)]);
      const restaurantData = restRes.data;
      const configData = configRes.data;
      // Backfill fields that may only exist in config for older restaurants
      if (restaurantData.delivery_enabled === undefined && configData?.delivery_enabled !== undefined) {
        restaurantData.delivery_enabled = configData.delivery_enabled;
      }
      if (restaurantData.pickup_enabled === undefined && configData?.pickup_enabled !== undefined) {
        restaurantData.pickup_enabled = configData.pickup_enabled;
      }
      // Parse address into structured fields for the form
      const addr = restaurantData.address || "";
      const parts = addr.split(",").map((s: string) => s.trim());
      const lastPart = parts[2] || "";
      const stateZip = lastPart.split(" ");
      restaurantData._street = parts[0] || "";
      restaurantData._city = parts[1] || "";
      restaurantData._state = stateZip[0] || "";
      restaurantData._zip = stateZip[1] || parts[3]?.trim() || "";
      setRestaurant(restaurantData);
      setConfig({ ...configData, operating_hours: { ...defaultHours, ...(configData?.operating_hours || {}) } });
      setBusinessType(configRes.data?.business_type || "restaurant");
    } catch {
      toast.error("Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, [activeRestaurant]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const saveRestaurant = async () => {
    setSaving(true);
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const payload: any = {
        name: restaurant?.name,
        address: `${restaurant?._street}, ${restaurant?._city}, ${restaurant?._state} ${restaurant?._zip}`.trim(),
        timezone: restaurant?.timezone,
        owner_name: restaurant?.owner_name,
        owner_email: restaurant?.owner_email,
        owner_phone: restaurant?.owner_phone,
        billing_email: restaurant?.billing_email,
        business_phone: restaurant?.business_phone,
        website: restaurant?.website,
        primary_language: restaurant?.primary_language,
      };

      // Restaurant-only fields
      if (!isAppointmentBusiness) {
        payload.cuisine_type = restaurant?.cuisine_type;
        payload.pickup_enabled = restaurant?.pickup_enabled;
        payload.delivery_enabled = restaurant?.delivery_enabled;
        payload.delivery_fee = Number(restaurant?.delivery_fee || 0);
        payload.delivery_radius_miles = Number(restaurant?.delivery_radius_miles || 5);
        payload.delivery_zip_codes = restaurant?.delivery_zip_codes || [];
        payload.delivery_eta_offset_minutes = Number(restaurant?.delivery_eta_offset_minutes || 15);
        payload.dine_in_enabled = restaurant?.dine_in_enabled;
        payload.reservations_enabled = restaurant?.reservations_enabled;
        payload.offers_delivery = restaurant?.offers_delivery;
        payload.offers_reservations = restaurant?.offers_reservations;
        payload.catering_enabled = restaurant?.catering_enabled;
        payload.avg_prep_time_minutes = Number(restaurant?.avg_prep_time_minutes || 0);
        payload.reservation_party_limit = Number(restaurant?.reservation_party_limit || 0);
      }

      if (restaurant?.reservations_enabled) {
        payload.reservation_slot_duration = Number(restaurant?.reservation_slot_duration || 30);
        payload.reservation_max_per_slot = Number(restaurant?.reservation_max_per_slot || 5);
        payload.reservation_advance_booking_days = Number(restaurant?.reservation_advance_booking_days || 7);
      }
      await updateRestaurant(restaurantId, payload);

      await refreshSession(restaurantId);
      toast.success(`${getBusinessLabel(businessType)} info saved!`);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const saveConfig = async () => {
    setSaving(true);
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const payload: any = {
        persona: config?.persona,
        voice_id: config?.voice_id,
        primary_language: config?.primary_language,
        business_rules: config?.business_rules,
        escalation_rules: config?.escalation_rules,
        disclosure_text: config?.disclosure_text,
        after_hours_mode: config?.after_hours_mode,
        voicemail_enabled: config?.voicemail_enabled,
        escalation_phone_number: config?.escalation_phone_number,
        operating_hours: config?.operating_hours,
      };

      // Restaurant-only config fields
      if (!isAppointmentBusiness) {
        payload.upsell_enabled = config?.upsell_enabled;
        payload.delivery_enabled = config?.delivery_enabled;
        payload.delivery_minimum = Number(config?.delivery_minimum || 0);
      }

      // Appointment-only config fields
      if (isAppointmentBusiness) {
        payload.slot_capacity = Number(config?.slot_capacity ?? 1);
        payload.slot_interval_minutes = Number(config?.slot_interval_minutes ?? 30);
      }

      await updateConfig(restaurantId, payload);
      await refreshSession(restaurantId);
      toast.success("AI configuration saved!");
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to save config");
    } finally {
      setSaving(false);
    }
  };

  const addRule = () => {
    if (!newRule.trim()) return;
    setConfig((prev: any) => ({ ...prev, business_rules: [...(prev.business_rules || []), newRule.trim()] }));
    setNewRule("");
  };
  const removeRule = (i: number) => setConfig((prev: any) => ({ ...prev, business_rules: prev.business_rules.filter((_: unknown, idx: number) => idx !== i) }));
  const addEscalation = () => {
    if (!newEscalation.trim()) return;
    setConfig((prev: any) => ({ ...prev, escalation_rules: [...(prev.escalation_rules || []), newEscalation.trim()] }));
    setNewEscalation("");
  };
  const removeEscalation = (i: number) => setConfig((prev: any) => ({ ...prev, escalation_rules: prev.escalation_rules.filter((_: unknown, idx: number) => idx !== i) }));
  const updateHours = (dayKey: keyof typeof defaultHours, field: string, value: any) => setConfig((prev: any) => ({ ...prev, operating_hours: { ...prev.operating_hours, [dayKey]: { ...prev.operating_hours[dayKey], [field]: value } } }));

  if (loading) return <div className="space-y-4">{[...Array(3)].map((_, i) => <Card key={i} className="premium-card h-40 animate-pulse" />)}</div>;

  return (
    <div className="max-w-5xl">
      <Tabs defaultValue="general" className="space-y-6">
        <TabsList className="bg-muted/50 rounded-xl p-1 h-auto flex-wrap">
          <TabsTrigger value="general" className="rounded-lg px-4 py-2 text-sm data-[state=active]:bg-card data-[state=active]:shadow-sm"><SettingsIcon className="w-4 h-4 mr-2" />General</TabsTrigger>
          <TabsTrigger value="ai" className="rounded-lg px-4 py-2 text-sm data-[state=active]:bg-card data-[state=active]:shadow-sm"><Mic className="w-4 h-4 mr-2" />Voice & AI</TabsTrigger>
          <TabsTrigger value="rules" className="rounded-lg px-4 py-2 text-sm data-[state=active]:bg-card data-[state=active]:shadow-sm"><ShieldAlert className="w-4 h-4 mr-2" />Rules</TabsTrigger>
        </TabsList>

        {/* ── GENERAL TAB ── */}
        <TabsContent value="general">
          <Card className="premium-card p-6 space-y-5">
            <div>
              <h3 className="font-display font-bold text-lg mb-1">Business Details</h3>
              <p className="text-sm text-muted-foreground">Update your {getBusinessLabel(businessType).toLowerCase()}'s operational details.</p>
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>{getBusinessLabel(businessType)} Name</Label>
                <Input value={restaurant?.name || ""} onChange={(e) => setRestaurant({ ...restaurant, name: e.target.value })} className="h-11 rounded-xl" />
              </div>

              {/* Cuisine type — restaurant only */}
              {!isAppointmentBusiness && (
                <div className="space-y-2">
                  <Label>{getSpecialtyLabel(businessType)}</Label>
                  <Input value={restaurant?.cuisine_type || ""} onChange={(e) => setRestaurant({ ...restaurant, cuisine_type: e.target.value })} className="h-11 rounded-xl" />
                </div>
              )}

              {/* Specialty — appointment businesses */}
              {isAppointmentBusiness && (
                <div className="space-y-2">
                  <Label>{getSpecialtyLabel(businessType)}</Label>
                  <Input value={restaurant?.cuisine_type || ""} onChange={(e) => setRestaurant({ ...restaurant, cuisine_type: e.target.value })} placeholder={businessType === "clinic" ? "e.g. Family Medicine, Dental" : businessType === "salon" ? "e.g. Hair, Nails, Spa" : businessType === "legal" ? "e.g. Family Law, Criminal" : "e.g. HVAC, Plumbing, Cleaning"} className="h-11 rounded-xl" />
                </div>
              )}

              <div className="space-y-2"><Label>Owner Name</Label><Input value={restaurant?.owner_name || ""} onChange={(e) => setRestaurant({ ...restaurant, owner_name: e.target.value })} className="h-11 rounded-xl" /></div>
              <div className="space-y-2"><Label>Owner Email</Label><Input value={restaurant?.owner_email || ""} onChange={(e) => setRestaurant({ ...restaurant, owner_email: e.target.value })} className="h-11 rounded-xl" /></div>
              <div className="space-y-2"><Label>Business Phone</Label><Input value={restaurant?.business_phone || ""} onChange={(e) => setRestaurant({ ...restaurant, business_phone: e.target.value })} className="h-11 rounded-xl" /></div>
              <div className="space-y-2"><Label>Billing Email</Label><Input value={restaurant?.billing_email || ""} onChange={(e) => setRestaurant({ ...restaurant, billing_email: e.target.value })} className="h-11 rounded-xl" /></div>
              <div className="space-y-2 sm:col-span-2"><Label>Street Address <span className="text-destructive">*</span></Label><Input value={restaurant?._street || ""} onChange={(e) => setRestaurant({ ...restaurant, _street: e.target.value })} placeholder="1520 W Ogden Ave" className="h-11 rounded-xl" /></div>
              <div className="space-y-2"><Label>City <span className="text-destructive">*</span></Label><Input value={restaurant?._city || ""} onChange={(e) => setRestaurant({ ...restaurant, _city: e.target.value })} placeholder="Naperville" className="h-11 rounded-xl" /></div>
              <div className="space-y-2">
                <Label>State <span className="text-destructive">*</span></Label>
                <Input value={restaurant?._state || ""} onChange={(e) => setRestaurant({ ...restaurant, _state: e.target.value })} placeholder="IL" maxLength={2} className="h-11 rounded-xl" />
              </div>
              <div className="space-y-2"><Label>Zip Code <span className="text-destructive">*</span></Label><Input value={restaurant?._zip || ""} onChange={(e) => setRestaurant({ ...restaurant, _zip: e.target.value })} placeholder="60540" maxLength={5} className="h-11 rounded-xl" /></div>
              <div className="space-y-2">
                <Label>Timezone</Label>
                <Select value={restaurant?.timezone || "America/Chicago"} onValueChange={(v) => setRestaurant({ ...restaurant, timezone: v })}>
                  <SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="America/New_York">Eastern</SelectItem>
                    <SelectItem value="America/Chicago">Central</SelectItem>
                    <SelectItem value="America/Denver">Mountain</SelectItem>
                    <SelectItem value="America/Los_Angeles">Pacific</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Primary Language</Label>
                <Select value={restaurant?.primary_language || "en"} onValueChange={(v) => setRestaurant({ ...restaurant, primary_language: v })}>
                  <SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="en">English</SelectItem>
                    <SelectItem value="es">Spanish</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Duuutah AI Phone Number</Label><Input value={restaurant?.phone_number || ""} readOnly className="h-11 rounded-xl opacity-60" /></div>

              {/* Avg prep time — restaurant only */}
              {!isAppointmentBusiness && (
                <div className="space-y-2">
                  <Label>Average Prep Time (minutes)</Label>
                  <Input type="number" value={restaurant?.avg_prep_time_minutes ?? 20} onChange={(e) => setRestaurant({ ...restaurant, avg_prep_time_minutes: Number(e.target.value || 0) })} className="h-11 rounded-xl" />
                </div>
              )}
            </div>

            {/* Restaurant-only toggles */}
            {!isAppointmentBusiness && (
              <div className="grid sm:grid-cols-2 gap-4">
                {[["pickup_enabled","Pickup Enabled"],["delivery_enabled","Delivery Enabled"],["reservations_enabled","Reservations Enabled"]].map(([key, label]) => {
                  const isGated = (key === "delivery_enabled" || key === "reservations_enabled") && restaurant?.plan !== "PRO";
                  return (
                    <div key={key} className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium">{label}</p>
                        {isGated && <span className="text-xs text-muted-foreground">(Pro)</span>}
                      </div>
                      <Switch checked={restaurant?.[key] ?? false} disabled={isGated} onCheckedChange={(v) => setRestaurant({ ...restaurant, [key]: v })} />
                    </div>
                  );
                })}
                  {[
                    { key: "offers_delivery", label: "Does your restaurant offer delivery?" },
                    { key: "offers_reservations", label: "Does your restaurant take reservations?" },
                  ].map(({ key, label }) => (
                    <div key={key} className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                      <span className="text-sm">{label}</span>
                      <div className="flex gap-2">
                        <button type="button" onClick={() => setRestaurant({ ...restaurant, [key]: true })} className={`px-3 py-1 text-xs rounded-lg font-medium transition-colors ${restaurant?.[key] !== false ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}>Yes</button>
                        <button type="button" onClick={() => setRestaurant({ ...restaurant, [key]: false })} className={`px-3 py-1 text-xs rounded-lg font-medium transition-colors ${restaurant?.[key] === false ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground"}`}>No</button>
                      </div>
                    </div>
                  ))}
              </div>
            )}

            {/* Reservation Settings (only when enabled) */}
            {!isAppointmentBusiness && restaurant?.reservations_enabled && (
              <div className="space-y-4 p-4 rounded-lg border border-primary/20 bg-primary/5">
                <h4 className="font-medium text-sm">Reservation Settings</h4>
                <div className="grid sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Max Party Size</Label>
                    <Input
                      type="number" min={1} max={50}
                      value={restaurant?.reservation_party_limit || 8}
                      onChange={(e) => setRestaurant({ ...restaurant, reservation_party_limit: parseInt(e.target.value) || 8 })}
                      className="h-9"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Max Reservations Per Slot</Label>
                    <Input
                      type="number" min={1} max={50}
                      value={restaurant?.reservation_max_per_slot || 5}
                      onChange={(e) => setRestaurant({ ...restaurant, reservation_max_per_slot: parseInt(e.target.value) || 5 })}
                      className="h-9"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Slot Duration (minutes)</Label>
                    <select
                      value={restaurant?.reservation_slot_duration || 30}
                      onChange={(e) => setRestaurant({ ...restaurant, reservation_slot_duration: parseInt(e.target.value) })}
                      className="w-full h-9 rounded-lg border border-border bg-card px-3 text-sm"
                    >
                      <option value={15}>15 min</option>
                      <option value={30}>30 min</option>
                      <option value={45}>45 min</option>
                      <option value={60}>60 min</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Advance Booking Days</Label>
                    <Input
                      type="number" min={1} max={90}
                      value={restaurant?.reservation_advance_booking_days || 7}
                      onChange={(e) => setRestaurant({ ...restaurant, reservation_advance_booking_days: parseInt(e.target.value) || 7 })}
                      className="h-9"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Delivery Settings (only when enabled) */}
            {!isAppointmentBusiness && restaurant?.delivery_enabled && (
              <div className="space-y-4 p-4 rounded-lg border border-primary/20 bg-primary/5">
                <h4 className="font-medium text-sm">Delivery Settings</h4>
                <div className="grid sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Delivery Minimum ($)</Label>
                    <Input type="number" value={((config?.delivery_minimum || 1500) / 100).toFixed(2)} onChange={(e) => setConfig({ ...config, delivery_minimum: Math.round(parseFloat(e.target.value || "0") * 100) })} step="0.01" min="0" className="h-9" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Delivery Fee ($)</Label>
                    <Input type="number" value={((restaurant?.delivery_fee || 0) / 100).toFixed(2)} onChange={(e) => setRestaurant({ ...restaurant, delivery_fee: Math.round(parseFloat(e.target.value || "0") * 100) })} step="0.01" min="0" placeholder="0 = free delivery" className="h-9" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Delivery Radius (miles)</Label>
                    <Input type="number" value={restaurant?.delivery_radius_miles || 5} onChange={(e) => setRestaurant({ ...restaurant, delivery_radius_miles: parseFloat(e.target.value) || 5 })} step="0.5" min="0.5" max="50" className="h-9" />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Extra Delivery Time (min)</Label>
                    <Input type="number" value={restaurant?.delivery_eta_offset_minutes || 15} onChange={(e) => setRestaurant({ ...restaurant, delivery_eta_offset_minutes: parseInt(e.target.value) || 15 })} min="0" max="60" className="h-9" />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Delivery Zip Codes (comma separated)</Label>
                  <Input value={(restaurant?.delivery_zip_codes || []).join(", ")} onChange={(e) => setRestaurant({ ...restaurant, delivery_zip_codes: e.target.value.split(",").map((z: string) => z.trim()).filter(Boolean) })} placeholder="60540, 60563, 60564" className="h-9" />
                  <p className="text-xs text-muted-foreground">AI will only accept delivery orders from these zip codes. Leave empty to accept all areas.</p>
                </div>
              </div>
            )}

            <Button onClick={saveRestaurant} disabled={saving} className="bg-gradient-primary text-primary-foreground rounded-xl shadow-glow hover:opacity-90">
              <Save className="w-4 h-4 mr-2" />{saving ? "Saving..." : "Save Changes"}
            </Button>
          </Card>
        </TabsContent>

        {/* ── VOICE & AI TAB ── */}
        <TabsContent value="ai">
          <Card className="premium-card p-6 space-y-5">
            <div><h3 className="font-display font-bold text-lg mb-1">AI Voice Settings</h3><p className="text-sm text-muted-foreground">Customize how your AI receptionist sounds and responds.</p></div>
            <div className="space-y-2">
              <Label>AI Persona</Label>
              <Select value={config?.persona || "friendly"} onValueChange={(v) => setConfig({ ...config, persona: v })}>
                <SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="friendly">Friendly & Warm</SelectItem>
                  <SelectItem value="professional">Professional & Formal</SelectItem>
                  <SelectItem value="casual">Casual & Relaxed</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Voice</Label>
              <div className="grid gap-2 mt-1">
                {voiceOptions.map((voice) => {
                  const isVoiceLocked = restaurant?.plan !== "PRO" && voice.id !== "Leda";
                  return (
                  <div key={voice.id} onClick={() => !isVoiceLocked && setConfig({ ...config, voice_id: voice.id })} className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${isVoiceLocked ? "opacity-50 cursor-not-allowed" : "cursor-pointer"} ${config?.voice_id === voice.id ? "border-primary bg-primary/5" : "border-border hover:border-primary/30"}`}>
                    <Volume2 className="w-4 h-4 text-muted-foreground" />
                    <div className="flex-1"><p className="text-sm font-medium">{voice.name}</p><p className="text-xs text-muted-foreground">{voice.accent}</p></div>
                    <div className="flex items-center gap-2">
                      {config?.voice_id === voice.id && <span className="text-xs bg-primary/10 text-primary rounded-full px-2 py-0.5">Selected</span>}
                      <button
                        onClick={(e) => { e.stopPropagation(); playVoicePreview(voice.id); }}
                        className="text-muted-foreground hover:text-primary transition-colors"
                        title="Preview voice"
                      >
                        <Volume2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    {isVoiceLocked && <span className="text-xs text-muted-foreground">Pro</span>}
                  </div>
                  );
                })}
              </div>
            </div>
            <div className="space-y-2"><Label>Custom Greeting</Label><Textarea value={config?.disclosure_text || ""} onChange={(e) => setConfig({ ...config, disclosure_text: e.target.value })} className="rounded-xl min-h-[80px]" /></div>
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Label>Primary Language</Label>
                  {restaurant?.plan !== "PRO" && <span className="text-xs text-muted-foreground">(Pro for multi-language)</span>}
                </div>
                <Select value={config?.primary_language || "en"} disabled={restaurant?.plan !== "PRO"} onValueChange={(v) => setConfig({ ...config, primary_language: v })}>
                  <SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="en">English</SelectItem><SelectItem value="es">Spanish</SelectItem></SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>After-hours Behavior</Label>
                <Select value={config?.after_hours_mode || "voicemail"} onValueChange={(v) => setConfig({ ...config, after_hours_mode: v })}>
                  <SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="voicemail">Take voicemail</SelectItem>
                    <SelectItem value="close_message">Play closed message</SelectItem>
                    <SelectItem value="forward">Forward to escalation number</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2"><Label>Escalation Phone Number</Label><Input value={config?.escalation_phone_number || ""} onChange={(e) => setConfig({ ...config, escalation_phone_number: e.target.value })} className="h-11 rounded-xl" /></div>
            <div className="grid sm:grid-cols-2 gap-4">
              {/* Upselling — restaurant only */}
              {!isAppointmentBusiness && (
                <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                  <div className="flex items-center gap-2">
                    <div><p className="text-sm font-medium">Upselling</p><p className="text-xs text-muted-foreground">Suggest add-ons after main order</p></div>
                    {restaurant?.plan !== "PRO" && <span className="text-xs text-muted-foreground">(Pro)</span>}
                  </div>
                  <Switch checked={config?.upsell_enabled || false} disabled={restaurant?.plan !== "PRO"} onCheckedChange={(v) => setConfig({ ...config, upsell_enabled: v })} />
                </div>
              )}
              
              <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                <div><p className="text-sm font-medium">Voicemail Enabled</p><p className="text-xs text-muted-foreground">Allow voicemail after hours</p></div>
                <Switch checked={config?.voicemail_enabled || false} onCheckedChange={(v) => setConfig({ ...config, voicemail_enabled: v })} />
              </div>
            </div>
            <div>
              <Label className="mb-3 block">Operating Hours</Label>
              <div className="space-y-3">
                {days.map(([key, label]) => {
                  const day = config?.operating_hours?.[key] || defaultHours[key];
                  return (
                    <div key={key} className="grid grid-cols-12 gap-2 items-center p-3 rounded-lg bg-muted/20">
                      <div className="col-span-3"><p className="text-sm font-medium">{label}</p></div>
                      <div className="col-span-2 flex items-center gap-2">
                        <input type="checkbox" className="accent-primary" checked={day.closed} onChange={(e) => updateHours(key, "closed", e.target.checked)} />
                        <span className="text-xs text-muted-foreground">Closed</span>
                      </div>
                      <div className="col-span-3"><Input type="time" value={day.open} disabled={day.closed} onChange={(e) => updateHours(key, "open", e.target.value)} /></div>
                      <div className="col-span-1 text-center text-xs text-muted-foreground">to</div>
                      <div className="col-span-3"><Input type="time" value={day.close} disabled={day.closed} onChange={(e) => updateHours(key, "close", e.target.value)} /></div>
                    </div>
                  );
                })}
              </div>
            </div>
            {/* Slot scheduling — appointment businesses only */}
            {isAppointmentBusiness && (
              <div className="space-y-3">
                <div>
                  <h4 className="text-sm font-semibold mb-1">Slot Scheduling</h4>
                  <p className="text-xs text-muted-foreground">
                    Controls how the AI checks and offers appointment times.
                  </p>
                </div>
                <div className="grid sm:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Slot Interval (minutes)</Label>
                    <Select
                      value={String(config?.slot_interval_minutes ?? 30)}
                      onValueChange={(v) => setConfig({ ...config, slot_interval_minutes: Number(v) })}
                    >
                      <SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="15">15 min</SelectItem>
                        <SelectItem value="20">20 min</SelectItem>
                        <SelectItem value="30">30 min</SelectItem>
                        <SelectItem value="45">45 min</SelectItem>
                        <SelectItem value="60">60 min</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Max Bookings per Slot</Label>
                    <Select
                      value={String(config?.slot_capacity ?? 1)}
                      onValueChange={(v) => setConfig({ ...config, slot_capacity: Number(v) })}
                    >
                      <SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {[1, 2, 3, 4, 5].map((n) => (
                          <SelectItem key={n} value={String(n)}>
                            {n} {n === 1 ? "booking" : "bookings"}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
            )}

            <Button onClick={saveConfig} disabled={saving} className="bg-gradient-primary text-primary-foreground rounded-xl shadow-glow hover:opacity-90">
              <Save className="w-4 h-4 mr-2" />{saving ? "Saving..." : "Save Config"}
            </Button>
          </Card>
        </TabsContent>

        {/* ── RULES TAB ── */}
        <TabsContent value="rules">
          <div className="space-y-4">
            <Card className="premium-card p-6 space-y-4">
              <div><h3 className="font-display font-bold text-lg mb-1">Business Rules</h3><p className="text-sm text-muted-foreground">Rules the AI will follow when handling calls.</p></div>
              <div className="space-y-2">
                {(config?.business_rules || []).map((rule: string, i: number) => (
                  <div key={i} className="flex items-center gap-2 p-2.5 rounded-lg bg-muted/30">
                    <span className="text-xs text-muted-foreground w-5">{i + 1}.</span>
                    <span className="text-sm flex-1">{rule}</span>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => removeRule(i)}><X className="w-3 h-3" /></Button>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <Input value={newRule} onChange={(e) => setNewRule(e.target.value)} placeholder="Add a business rule..." onKeyDown={(e) => e.key === "Enter" && addRule()} />
                <Button variant="outline" size="sm" onClick={addRule}><Plus className="w-4 h-4" /></Button>
              </div>
            </Card>
            <Card className="premium-card p-6 space-y-4">
              <div><h3 className="font-display font-bold text-lg mb-1 flex items-center gap-2"><ShieldAlert className="w-4 h-4" />Escalation Triggers</h3><p className="text-sm text-muted-foreground">Situations where AI should transfer to a human.</p></div>
              <div className="space-y-2">
                {(config?.escalation_rules || []).map((rule: string, i: number) => (
                  <div key={i} className="flex items-center gap-2 p-2.5 rounded-lg bg-warning/5">
                    <AlertTriangle className="w-3.5 h-3.5 text-warning shrink-0" />
                    <span className="text-sm flex-1">{rule}</span>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => removeEscalation(i)}><X className="w-3 h-3" /></Button>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <Input value={newEscalation} onChange={(e) => setNewEscalation(e.target.value)} placeholder="Add escalation trigger..." onKeyDown={(e) => e.key === "Enter" && addEscalation()} />
                <Button variant="outline" size="sm" onClick={addEscalation}><Plus className="w-4 h-4" /></Button>
              </div>
            </Card>
            <Button onClick={saveConfig} disabled={saving} className="bg-gradient-primary text-primary-foreground rounded-xl shadow-glow hover:opacity-90">
              <Save className="w-4 h-4 mr-2" />{saving ? "Saving..." : "Save All Rules"}
            </Button>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default SettingsPage;
