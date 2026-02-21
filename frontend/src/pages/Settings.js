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
import { getRestaurant, updateRestaurant, getConfig, updateConfig, getTestModeStatus } from "@/lib/api";
import { toast } from "sonner";

const voiceOptions = [
  { id: "21m00Tcm4TlvDq8ikWAM", name: "Rachel - Professional", accent: "American" },
  { id: "AZnzlk1XvdvUeBnXmlld", name: "Domi - Warm", accent: "American" },
  { id: "EXAVITQu4vr4xnSDxMaL", name: "Bella - Friendly", accent: "American" },
  { id: "TX3LPaxmHKxFdv7VOQHJ", name: "Liam - Calm", accent: "American" },
  { id: "onwK4e9ZLuTAKqWW03F9", name: "Daniel - Authoritative", accent: "British" },
];

export default function Settings() {
  const [restaurant, setRestaurant] = useState(null);
  const [config, setConfig] = useState(null);
  const [testMode, setTestMode] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newRule, setNewRule] = useState("");
  const [newEscalation, setNewEscalation] = useState("");

  const fetchData = useCallback(async () => {
    try {
      const [restRes, configRes, testModeRes] = await Promise.all([
        getRestaurant(), 
        getConfig(),
        getTestModeStatus(),
      ]);
      setRestaurant(restRes.data);
      setConfig(configRes.data);
      setTestMode(testModeRes.data);
    } catch (err) {
      toast.error("Failed to load settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const saveRestaurant = async () => {
    setSaving(true);
    try {
      await updateRestaurant(null, {
        name: restaurant.name,
        cuisine_type: restaurant.cuisine_type,
        address: restaurant.address,
        timezone: restaurant.timezone,
      });
      toast.success("Restaurant info saved!");
    } catch (err) {
      toast.error("Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const saveConfig = async () => {
    setSaving(true);
    try {
      await updateConfig(null, {
        persona: config.persona,
        voice_id: config.voice_id,
        business_rules: config.business_rules,
        escalation_rules: config.escalation_rules,
        upsell_enabled: config.upsell_enabled,
        disclosure_text: config.disclosure_text,
        delivery_enabled: config.delivery_enabled,
        delivery_minimum: config.delivery_minimum,
      });
      toast.success("AI configuration saved!");
    } catch (err) {
      toast.error("Failed to save config");
    } finally {
      setSaving(false);
    }
  };

  const addRule = () => {
    if (!newRule.trim()) return;
    setConfig(prev => ({ ...prev, business_rules: [...(prev.business_rules || []), newRule.trim()] }));
    setNewRule("");
  };

  const removeRule = (i) => {
    setConfig(prev => ({ ...prev, business_rules: prev.business_rules.filter((_, idx) => idx !== i) }));
  };

  const addEscalation = () => {
    if (!newEscalation.trim()) return;
    setConfig(prev => ({ ...prev, escalation_rules: [...(prev.escalation_rules || []), newEscalation.trim()] }));
    setNewEscalation("");
  };

  const removeEscalation = (i) => {
    setConfig(prev => ({ ...prev, escalation_rules: prev.escalation_rules.filter((_, idx) => idx !== i) }));
  };

  if (loading) {
    return (
      <AppLayout>
        <div className="p-6">
          <div className="space-y-4">
            {[...Array(3)].map((_, i) => <Card key={i} className="p-6 animate-pulse border-border bg-card"><div className="h-40 bg-muted rounded" /></Card>)}
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
          <TabsList className="grid w-full max-w-lg grid-cols-4">
            <TabsTrigger value="general" className="text-xs">General</TabsTrigger>
            <TabsTrigger value="voice" className="text-xs">Voice & AI</TabsTrigger>
            <TabsTrigger value="rules" className="text-xs">Rules</TabsTrigger>
            <TabsTrigger value="billing" className="text-xs">Billing</TabsTrigger>
          </TabsList>

          {/* General Tab */}
          <TabsContent value="general" className="mt-4">
            <Card className="p-6 border-border bg-card">
              <h3 className="text-base font-heading font-semibold text-foreground mb-4 flex items-center gap-2">
                <SettingsIcon className="w-4 h-4" /> Restaurant Information
              </h3>
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <Label className="text-xs">Restaurant Name</Label>
                  <Input value={restaurant?.name || ""} onChange={(e) => setRestaurant({ ...restaurant, name: e.target.value })} />
                </div>
                <div>
                  <Label className="text-xs">Cuisine Type</Label>
                  <Input value={restaurant?.cuisine_type || ""} onChange={(e) => setRestaurant({ ...restaurant, cuisine_type: e.target.value })} />
                </div>
                <div className="sm:col-span-2">
                  <Label className="text-xs">Address</Label>
                  <Input value={restaurant?.address || ""} onChange={(e) => setRestaurant({ ...restaurant, address: e.target.value })} />
                </div>
                <div>
                  <Label className="text-xs">Timezone</Label>
                  <Select value={restaurant?.timezone || "America/New_York"} onValueChange={(v) => setRestaurant({ ...restaurant, timezone: v })}>
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
                  <Label className="text-xs">Phone Number</Label>
                  <Input value={restaurant?.phone_number || ""} disabled className="bg-muted" />
                </div>
              </div>
              <div className="mt-4">
                <Button variant="premium" size="sm" onClick={saveRestaurant} disabled={saving}>
                  <Save className="w-4 h-4" /> {saving ? "Saving..." : "Save Changes"}
                </Button>
              </div>
            </Card>
          </TabsContent>

          {/* Voice & AI Tab */}
          <TabsContent value="voice" className="mt-4 space-y-4">
            <Card className="p-6 border-border bg-card">
              <h3 className="text-base font-heading font-semibold text-foreground mb-4 flex items-center gap-2">
                <Mic className="w-4 h-4" /> Voice & Persona
              </h3>
              <div className="space-y-4">
                <div>
                  <Label className="text-xs">AI Persona</Label>
                  <Select value={config?.persona || "friendly"} onValueChange={(v) => setConfig({ ...config, persona: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="friendly">Friendly & Warm</SelectItem>
                      <SelectItem value="professional">Professional & Formal</SelectItem>
                      <SelectItem value="casual">Casual & Relaxed</SelectItem>
                      <SelectItem value="warm and friendly Italian-American">Italian-American Warmth</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Voice</Label>
                  <div className="grid gap-2 mt-1">
                    {voiceOptions.map(voice => (
                      <div
                        key={voice.id}
                        onClick={() => setConfig({ ...config, voice_id: voice.id })}
                        className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                          config?.voice_id === voice.id ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/30'
                        }`}
                      >
                        <Volume2 className="w-4 h-4 text-muted-foreground" />
                        <div className="flex-1">
                          <p className="text-sm font-medium text-foreground">{voice.name}</p>
                          <p className="text-xs text-muted-foreground">{voice.accent}</p>
                        </div>
                        {config?.voice_id === voice.id && (
                          <Badge variant="secondary" className="bg-primary/10 text-primary border-0 text-xs">Selected</Badge>
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
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-foreground">Upselling</p>
                    <p className="text-xs text-muted-foreground">Suggest add-ons after main order</p>
                  </div>
                  <Switch checked={config?.upsell_enabled || false} onCheckedChange={(v) => setConfig({ ...config, upsell_enabled: v })} />
                </div>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-foreground">Delivery Orders</p>
                    <p className="text-xs text-muted-foreground">Accept delivery orders via phone</p>
                  </div>
                  <Switch checked={config?.delivery_enabled || false} onCheckedChange={(v) => setConfig({ ...config, delivery_enabled: v })} />
                </div>
                <Button variant="premium" size="sm" onClick={saveConfig} disabled={saving}>
                  <Save className="w-4 h-4" /> {saving ? "Saving..." : "Save Config"}
                </Button>
              </div>
            </Card>
          </TabsContent>

          {/* Rules Tab */}
          <TabsContent value="rules" className="mt-4 space-y-4">
            {/* Business Rules */}
            <Card className="p-6 border-border bg-card">
              <h3 className="text-base font-heading font-semibold text-foreground mb-4">Business Rules</h3>
              <p className="text-xs text-muted-foreground mb-4">Rules the AI will follow when handling calls</p>
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
                <Input value={newRule} onChange={(e) => setNewRule(e.target.value)} placeholder="Add a business rule..." onKeyDown={(e) => e.key === 'Enter' && addRule()} />
                <Button variant="outline" size="sm" onClick={addRule}><Plus className="w-4 h-4" /></Button>
              </div>
            </Card>

            {/* Escalation Rules */}
            <Card className="p-6 border-border bg-card">
              <h3 className="text-base font-heading font-semibold text-foreground mb-4 flex items-center gap-2">
                <ShieldAlert className="w-4 h-4" /> Escalation Triggers
              </h3>
              <p className="text-xs text-muted-foreground mb-4">Situations where AI should transfer to a human</p>
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
                <Input value={newEscalation} onChange={(e) => setNewEscalation(e.target.value)} placeholder="Add escalation trigger..." onKeyDown={(e) => e.key === 'Enter' && addEscalation()} />
                <Button variant="outline" size="sm" onClick={addEscalation}><Plus className="w-4 h-4" /></Button>
              </div>
            </Card>

            <Button variant="premium" size="sm" onClick={saveConfig} disabled={saving}>
              <Save className="w-4 h-4" /> {saving ? "Saving..." : "Save All Rules"}
            </Button>
          </TabsContent>

          {/* Billing Tab */}
          <TabsContent value="billing" className="mt-4">
            <Card className="p-6 border-border bg-card">
              <h3 className="text-base font-heading font-semibold text-foreground mb-4 flex items-center gap-2">
                <CreditCard className="w-4 h-4" /> Billing & Plan
              </h3>
              <div className="flex items-center gap-4 p-4 rounded-lg bg-primary/5 border border-primary/20 mb-6">
                <div className="flex-1">
                  <p className="text-sm font-heading font-semibold text-foreground">Growth Plan</p>
                  <p className="text-xs text-muted-foreground">$399/month · Unlimited calls · Up to 3 locations</p>
                </div>
                <Badge variant="secondary" className="bg-primary/10 text-primary border-0">Active</Badge>
              </div>
              <div className="grid sm:grid-cols-3 gap-4">
                <div className="p-4 rounded-lg bg-muted/30">
                  <p className="text-xs text-muted-foreground">Monthly Calls</p>
                  <p className="text-lg font-heading font-bold text-foreground">{restaurant?.monthly_call_count || 0}</p>
                </div>
                <div className="p-4 rounded-lg bg-muted/30">
                  <p className="text-xs text-muted-foreground">Plan Limit</p>
                  <p className="text-lg font-heading font-bold text-foreground">Unlimited</p>
                </div>
                <div className="p-4 rounded-lg bg-muted/30">
                  <p className="text-xs text-muted-foreground">Next Billing</p>
                  <p className="text-lg font-heading font-bold text-foreground">Mar 1, 2026</p>
                </div>
              </div>
              <Separator className="my-6" />
              <Button variant="outline" size="sm">Manage Subscription</Button>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
}
