import { useCallback, useEffect, useState } from "react";
import { useAppSession } from "@/context/AppSessionContext";
import { getConfig, getRestaurant, getRestaurantId, updateConfig, updateRestaurant } from "@/lib/api";
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
const days: [keyof typeof defaultHours, string][] = [["monday","Monday"],["tuesday","Tuesday"],["wednesday","Wednesday"],["thursday","Thursday"],["friday","Friday"],["saturday","Saturday"],["sunday","Sunday"]];

const SettingsPage = () => {
  const { activeRestaurant, refreshSession } = useAppSession();
  const [restaurant, setRestaurant] = useState<any>(null);
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newRule, setNewRule] = useState("");
  const [newEscalation, setNewEscalation] = useState("");

  const fetchData = useCallback(async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const [restRes, configRes] = await Promise.all([getRestaurant(restaurantId), getConfig(restaurantId)]);
      setRestaurant(restRes.data);
      setConfig({ ...configRes.data, operating_hours: { ...defaultHours, ...(configRes.data?.operating_hours || {}) } });
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
      toast.success("Restaurant info saved!");
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

        <TabsContent value="general">
          <Card className="premium-card p-6 space-y-5">
            <div><h3 className="font-display font-bold text-lg mb-1">Restaurant Details</h3><p className="text-sm text-muted-foreground">Update your restaurant's operational details.</p></div>
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="space-y-2"><Label>Restaurant Name</Label><Input value={restaurant?.name || ""} onChange={(e) => setRestaurant({ ...restaurant, name: e.target.value })} className="h-11 rounded-xl" /></div>
              <div className="space-y-2"><Label>Cuisine Type</Label><Input value={restaurant?.cuisine_type || ""} onChange={(e) => setRestaurant({ ...restaurant, cuisine_type: e.target.value })} className="h-11 rounded-xl" /></div>
              <div className="space-y-2"><Label>Owner Name</Label><Input value={restaurant?.owner_name || ""} onChange={(e) => setRestaurant({ ...restaurant, owner_name: e.target.value })} className="h-11 rounded-xl" /></div>
              <div className="space-y-2"><Label>Owner Email</Label><Input value={restaurant?.owner_email || ""} onChange={(e) => setRestaurant({ ...restaurant, owner_email: e.target.value })} className="h-11 rounded-xl" /></div>
              <div className="space-y-2"><Label>Business Phone</Label><Input value={restaurant?.business_phone || ""} onChange={(e) => setRestaurant({ ...restaurant, business_phone: e.target.value })} className="h-11 rounded-xl" /></div>
              <div className="space-y-2"><Label>Billing Email</Label><Input value={restaurant?.billing_email || ""} onChange={(e) => setRestaurant({ ...restaurant, billing_email: e.target.value })} className="h-11 rounded-xl" /></div>
              <div className="space-y-2 sm:col-span-2"><Label>Address</Label><Input value={restaurant?.address || ""} onChange={(e) => setRestaurant({ ...restaurant, address: e.target.value })} className="h-11 rounded-xl" /></div>
              <div className="space-y-2"><Label>Timezone</Label><Select value={restaurant?.timezone || "America/Chicago"} onValueChange={(v) => setRestaurant({ ...restaurant, timezone: v })}><SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="America/New_York">Eastern</SelectItem><SelectItem value="America/Chicago">Central</SelectItem><SelectItem value="America/Denver">Mountain</SelectItem><SelectItem value="America/Los_Angeles">Pacific</SelectItem></SelectContent></Select></div>
              <div className="space-y-2"><Label>Primary Language</Label><Select value={restaurant?.primary_language || "en"} onValueChange={(v) => setRestaurant({ ...restaurant, primary_language: v })}><SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="en">English</SelectItem><SelectItem value="es">Spanish</SelectItem></SelectContent></Select></div>
              <div className="space-y-2"><Label>Phone Number</Label><Input value={restaurant?.phone_number || ""} readOnly className="h-11 rounded-xl" /></div>
              <div className="space-y-2"><Label>Average Prep Time (minutes)</Label><Input type="number" value={restaurant?.avg_prep_time_minutes ?? 20} onChange={(e) => setRestaurant({ ...restaurant, avg_prep_time_minutes: Number(e.target.value || 0) })} className="h-11 rounded-xl" /></div>
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              {[["pickup_enabled","Pickup Enabled"],["delivery_enabled","Delivery Enabled"],["dine_in_enabled","Dine-in Enabled"],["reservations_enabled","Reservations Enabled"]].map(([key, label]) => <div key={key} className="flex items-center justify-between p-3 rounded-lg bg-muted/30"><p className="text-sm font-medium">{label}</p><Switch checked={restaurant?.[key] ?? false} onCheckedChange={(v) => setRestaurant({ ...restaurant, [key]: v })} /></div>)}
            </div>
            <Button onClick={saveRestaurant} disabled={saving} className="bg-gradient-primary text-primary-foreground rounded-xl shadow-glow hover:opacity-90"><Save className="w-4 h-4 mr-2" />{saving ? "Saving..." : "Save Changes"}</Button>
          </Card>
        </TabsContent>

        <TabsContent value="ai">
          <Card className="premium-card p-6 space-y-5">
            <div><h3 className="font-display font-bold text-lg mb-1">AI Voice Settings</h3><p className="text-sm text-muted-foreground">Customize how your AI receptionist sounds and responds.</p></div>
            <div className="space-y-2"><Label>AI Persona</Label><Select value={config?.persona || "friendly"} onValueChange={(v) => setConfig({ ...config, persona: v })}><SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="friendly">Friendly & Warm</SelectItem><SelectItem value="professional">Professional & Formal</SelectItem><SelectItem value="casual">Casual & Relaxed</SelectItem></SelectContent></Select></div>
            <div className="space-y-2"><Label>Voice</Label><div className="grid gap-2 mt-1">{voiceOptions.map((voice) => <div key={voice.id} onClick={() => setConfig({ ...config, voice_id: voice.id })} className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${config?.voice_id === voice.id ? "border-primary bg-primary/5" : "border-border hover:border-primary/30"}`}><Volume2 className="w-4 h-4 text-muted-foreground" /><div className="flex-1"><p className="text-sm font-medium">{voice.name}</p><p className="text-xs text-muted-foreground">{voice.accent}</p></div>{config?.voice_id === voice.id && <span className="text-xs bg-primary/10 text-primary rounded-full px-2 py-0.5">Selected</span>}</div>)}</div></div>
            <div className="space-y-2"><Label>Custom Greeting</Label><Textarea value={config?.disclosure_text || ""} onChange={(e) => setConfig({ ...config, disclosure_text: e.target.value })} className="rounded-xl min-h-[80px]" /></div>
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="space-y-2"><Label>Primary Language</Label><Select value={config?.primary_language || "en"} onValueChange={(v) => setConfig({ ...config, primary_language: v })}><SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="en">English</SelectItem><SelectItem value="es">Spanish</SelectItem></SelectContent></Select></div>
              <div className="space-y-2"><Label>After-hours Behavior</Label><Select value={config?.after_hours_mode || "voicemail"} onValueChange={(v) => setConfig({ ...config, after_hours_mode: v })}><SelectTrigger className="h-11 rounded-xl"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="voicemail">Take voicemail</SelectItem><SelectItem value="close_message">Play closed message</SelectItem><SelectItem value="forward">Forward to escalation number</SelectItem></SelectContent></Select></div>
            </div>
            <div className="space-y-2"><Label>Escalation Phone Number</Label><Input value={config?.escalation_phone_number || ""} onChange={(e) => setConfig({ ...config, escalation_phone_number: e.target.value })} className="h-11 rounded-xl" /></div>
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30"><div><p className="text-sm font-medium">Upselling</p><p className="text-xs text-muted-foreground">Suggest add-ons after main order</p></div><Switch checked={config?.upsell_enabled || false} onCheckedChange={(v) => setConfig({ ...config, upsell_enabled: v })} /></div>
              <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30"><div><p className="text-sm font-medium">Voicemail Enabled</p><p className="text-xs text-muted-foreground">Allow voicemail after hours</p></div><Switch checked={config?.voicemail_enabled || false} onCheckedChange={(v) => setConfig({ ...config, voicemail_enabled: v })} /></div>
            </div>
            <div>
              <Label className="mb-3 block">Operating Hours</Label>
              <div className="space-y-3">
                {days.map(([key, label]) => { const day = config?.operating_hours?.[key] || defaultHours[key]; return <div key={key} className="grid grid-cols-12 gap-2 items-center p-3 rounded-lg bg-muted/20"><div className="col-span-3"><p className="text-sm font-medium">{label}</p></div><div className="col-span-2 flex items-center gap-2"><input type="checkbox" className="accent-primary" checked={day.closed} onChange={(e) => updateHours(key, "closed", e.target.checked)} /><span className="text-xs text-muted-foreground">Closed</span></div><div className="col-span-3"><Input type="time" value={day.open} disabled={day.closed} onChange={(e) => updateHours(key, "open", e.target.value)} /></div><div className="col-span-1 text-center text-xs text-muted-foreground">to</div><div className="col-span-3"><Input type="time" value={day.close} disabled={day.closed} onChange={(e) => updateHours(key, "close", e.target.value)} /></div></div>; })}
              </div>
            </div>
            <Button onClick={saveConfig} disabled={saving} className="bg-gradient-primary text-primary-foreground rounded-xl shadow-glow hover:opacity-90"><Save className="w-4 h-4 mr-2" />{saving ? "Saving..." : "Save Config"}</Button>
          </Card>
        </TabsContent>

        <TabsContent value="rules">
          <div className="space-y-4">
            <Card className="premium-card p-6 space-y-4">
              <div><h3 className="font-display font-bold text-lg mb-1">Business Rules</h3><p className="text-sm text-muted-foreground">Rules the AI will follow when handling calls.</p></div>
              <div className="space-y-2">{(config?.business_rules || []).map((rule: string, i: number) => <div key={i} className="flex items-center gap-2 p-2.5 rounded-lg bg-muted/30"><span className="text-xs text-muted-foreground w-5">{i + 1}.</span><span className="text-sm flex-1">{rule}</span><Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => removeRule(i)}><X className="w-3 h-3" /></Button></div>)}</div>
              <div className="flex gap-2"><Input value={newRule} onChange={(e) => setNewRule(e.target.value)} placeholder="Add a business rule..." onKeyDown={(e) => e.key === "Enter" && addRule()} /><Button variant="outline" size="sm" onClick={addRule}><Plus className="w-4 h-4" /></Button></div>
            </Card>
            <Card className="premium-card p-6 space-y-4">
              <div><h3 className="font-display font-bold text-lg mb-1 flex items-center gap-2"><ShieldAlert className="w-4 h-4" />Escalation Triggers</h3><p className="text-sm text-muted-foreground">Situations where AI should transfer to a human.</p></div>
              <div className="space-y-2">{(config?.escalation_rules || []).map((rule: string, i: number) => <div key={i} className="flex items-center gap-2 p-2.5 rounded-lg bg-warning/5"><AlertTriangle className="w-3.5 h-3.5 text-warning shrink-0" /><span className="text-sm flex-1">{rule}</span><Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => removeEscalation(i)}><X className="w-3 h-3" /></Button></div>)}</div>
              <div className="flex gap-2"><Input value={newEscalation} onChange={(e) => setNewEscalation(e.target.value)} placeholder="Add escalation trigger..." onKeyDown={(e) => e.key === "Enter" && addEscalation()} /><Button variant="outline" size="sm" onClick={addEscalation}><Plus className="w-4 h-4" /></Button></div>
            </Card>
            <Button onClick={saveConfig} disabled={saving} className="bg-gradient-primary text-primary-foreground rounded-xl shadow-glow hover:opacity-90"><Save className="w-4 h-4 mr-2" />{saving ? "Saving..." : "Save All Rules"}</Button>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default SettingsPage;
