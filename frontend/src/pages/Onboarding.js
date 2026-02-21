import { useState } from "react";
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
  Phone,
  PhoneCall,
} from "lucide-react";
import { toast } from "sonner";
import { motion, AnimatePresence } from "framer-motion";
import api, { setRestaurantId, confirmMenu, activateRestaurant } from "@/lib/api";

const steps = [
  { id: 1, label: "Restaurant Info", icon: UtensilsCrossed },
  { id: 2, label: "Menu Setup", icon: FileText },
  { id: 3, label: "AI Configuration", icon: Settings },
  { id: 4, label: "Go Live", icon: Rocket },
];

export default function Onboarding() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [restaurantData, setRestaurantData] = useState({
    name: "", cuisine_type: "", address: "", timezone: "America/New_York",
  });
  const [restaurantIdState, setRestaurantIdState] = useState(null);
  const [menuText, setMenuText] = useState("");
  const [parsedItems, setParsedItems] = useState([]);
  const [parsing, setParsing] = useState(false);
  const [aiConfig, setAiConfig] = useState({
    persona: "friendly", disclosure_text: "", upsell_enabled: true,
  });
  const [activating, setActivating] = useState(false);
  const [activated, setActivated] = useState(false);

  const createRestaurant = async () => {
    if (!restaurantData.name.trim()) { toast.error("Restaurant name is required"); return; }
    try {
      const res = await api.post("/restaurants", restaurantData);
      const newId = res.data.id;
      setRestaurantId(newId); // Save to localStorage
      setRestaurantIdState(newId);
      setAiConfig(prev => ({
        ...prev,
        disclosure_text: `Hi! I'm an AI assistant for ${restaurantData.name}. How can I help you today?`
      }));
      toast.success("Restaurant created!");
      setStep(2);
    } catch (err) {
      toast.error("Failed to create restaurant");
    }
  };

  const parseMenu = async () => {
    if (!menuText.trim()) { toast.error("Please enter your menu text"); return; }
    setParsing(true);
    try {
      const res = await api.post("/onboarding/menu/parse", {
        menu_text: menuText, restaurant_id: restaurantIdState,
      });
      setParsedItems(res.data.items || []);
      if (res.data.items?.length > 0) {
        toast.success(`Parsed ${res.data.items.length} menu items!`);
      } else {
        toast.warning("No items could be parsed. Try a different format.");
      }
    } catch (err) {
      toast.error("Failed to parse menu");
    } finally {
      setParsing(false);
    }
  };

  const saveMenuAndProceed = async () => {
    if (parsedItems.length === 0) { toast.warning("Parse your menu first"); return; }
    try {
      await confirmMenu(restaurantIdState, parsedItems);
      toast.success("Menu saved!");
      setStep(3);
    } catch (err) {
      toast.error("Failed to save menu");
    }
  };

  const saveConfigAndProceed = async () => {
    try {
      await api.put(`/restaurants/${restaurantIdState}/config`, aiConfig);
      toast.success("AI configuration saved!");
      setStep(4);
    } catch (err) {
      toast.error("Failed to save config");
    }
  };

  const goLive = async () => {
    setActivating(true);
    try {
      await activateRestaurant(restaurantIdState);
      setActivated(true);
      toast.success("Your AI phone agent is live!");
    } catch (err) {
      toast.error("Failed to activate");
    } finally {
      setActivating(false);
    }
  };

  const progress = (step / steps.length) * 100;

  return (
    <div className="min-h-screen bg-background">
      {/* Top Bar */}
      <div className="border-b border-border bg-card px-4 lg:px-8 py-4">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <a href="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-primary flex items-center justify-center">
              <PhoneCall className="w-4 h-4 text-primary-foreground" />
            </div>
            <span className="text-lg font-heading font-bold text-foreground">
              ring<span className="text-gradient-primary">AI</span>
            </span>
          </a>
          <Badge variant="secondary" className="text-xs">Setup Wizard</Badge>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 lg:px-8 py-8">
        {/* Progress */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-3">
            {steps.map((s, i) => (
              <div key={s.id} className="flex items-center gap-2">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold ${
                  step > s.id ? 'bg-primary text-primary-foreground' :
                  step === s.id ? 'bg-primary text-primary-foreground' :
                  'bg-muted text-muted-foreground'
                }`}>
                  {step > s.id ? <Check className="w-4 h-4" /> : s.id}
                </div>
                <span className={`hidden sm:block text-xs font-medium ${
                  step >= s.id ? 'text-foreground' : 'text-muted-foreground'
                }`}>{s.label}</span>
                {i < steps.length - 1 && <div className="hidden sm:block w-8 lg:w-16 h-px bg-border" />}
              </div>
            ))}
          </div>
          <Progress value={progress} className="h-1" />
        </div>

        {/* Step Content */}
        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.3 }}
          >
            {/* Step 1: Restaurant Info */}
            {step === 1 && (
              <Card className="p-6 lg:p-8 border-border bg-card">
                <h2 className="text-xl font-heading font-bold text-foreground mb-1">Tell us about your restaurant</h2>
                <p className="text-sm text-muted-foreground mb-6">We'll use this to customize your AI phone agent.</p>
                <div className="space-y-4">
                  <div>
                    <Label className="text-xs">Restaurant Name *</Label>
                    <Input value={restaurantData.name} onChange={(e) => setRestaurantData({ ...restaurantData, name: e.target.value })} placeholder="Bella Cucina" />
                  </div>
                  <div>
                    <Label className="text-xs">Cuisine Type</Label>
                    <Input value={restaurantData.cuisine_type} onChange={(e) => setRestaurantData({ ...restaurantData, cuisine_type: e.target.value })} placeholder="Italian, Mexican, Chinese..." />
                  </div>
                  <div>
                    <Label className="text-xs">Address</Label>
                    <Input value={restaurantData.address} onChange={(e) => setRestaurantData({ ...restaurantData, address: e.target.value })} placeholder="123 Main St, City, State" />
                  </div>
                  <div>
                    <Label className="text-xs">Timezone</Label>
                    <Select value={restaurantData.timezone} onValueChange={(v) => setRestaurantData({ ...restaurantData, timezone: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="America/New_York">Eastern</SelectItem>
                        <SelectItem value="America/Chicago">Central</SelectItem>
                        <SelectItem value="America/Denver">Mountain</SelectItem>
                        <SelectItem value="America/Los_Angeles">Pacific</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="pt-2">
                    <Button variant="premium" onClick={createRestaurant} className="w-full">
                      Continue <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </Card>
            )}

            {/* Step 2: Menu Setup */}
            {step === 2 && (
              <Card className="p-6 lg:p-8 border-border bg-card">
                <h2 className="text-xl font-heading font-bold text-foreground mb-1">Upload Your Menu</h2>
                <p className="text-sm text-muted-foreground mb-6">Paste your menu text and our AI will parse it into structured data.</p>
                <div className="space-y-4">
                  <div>
                    <Label className="text-xs">Menu Text</Label>
                    <Textarea
                      value={menuText}
                      onChange={(e) => setMenuText(e.target.value)}
                      placeholder={"APPETIZERS\nBruschetta - $12.99\nCalamari Fritti - $14.99\n\nPASTA\nSpaghetti Bolognese - $18.99\nFettuccine Alfredo - $17.99"}
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
                        <p className="text-xs font-medium text-foreground">{parsedItems.length} items parsed</p>
                      </div>
                      <div className="divide-y divide-border max-h-64 overflow-y-auto">
                        {parsedItems.map((item, i) => (
                          <div key={i} className="flex items-center justify-between px-4 py-2">
                            <div>
                              <p className="text-sm text-foreground">{item.name}</p>
                              <p className="text-xs text-muted-foreground">{item.category}</p>
                            </div>
                            <span className="text-sm font-medium text-foreground">
                              {item.price ? `$${(item.price / 100).toFixed(2)}` : '--'}
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
                    <Button variant="premium" onClick={saveMenuAndProceed} className="flex-1" disabled={parsedItems.length === 0}>
                      Save & Continue <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </Card>
            )}

            {/* Step 3: AI Config */}
            {step === 3 && (
              <Card className="p-6 lg:p-8 border-border bg-card">
                <h2 className="text-xl font-heading font-bold text-foreground mb-1">Configure Your AI Agent</h2>
                <p className="text-sm text-muted-foreground mb-6">Customize how your AI phone agent sounds and behaves.</p>
                <div className="space-y-4">
                  <div>
                    <Label className="text-xs">Persona</Label>
                    <Select value={aiConfig.persona} onValueChange={(v) => setAiConfig({ ...aiConfig, persona: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
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
                  <div className="flex items-center justify-between p-3 rounded-lg bg-muted/30">
                    <div>
                      <p className="text-sm font-medium text-foreground">Enable Upselling</p>
                      <p className="text-xs text-muted-foreground">AI suggests add-ons and sides</p>
                    </div>
                    <input type="checkbox" checked={aiConfig.upsell_enabled} onChange={(e) => setAiConfig({ ...aiConfig, upsell_enabled: e.target.checked })} className="accent-primary" />
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

            {/* Step 4: Go Live */}
            {step === 4 && (
              <Card className="p-6 lg:p-8 border-border bg-card text-center">
                {!activated ? (
                  <>
                    <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-4">
                      <Rocket className="w-8 h-8 text-primary" />
                    </div>
                    <h2 className="text-xl font-heading font-bold text-foreground mb-2">Ready to Go Live!</h2>
                    <p className="text-sm text-muted-foreground mb-6">Your AI phone agent is configured and ready. Activating will assign a phone number and start accepting calls.</p>
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
                    <h2 className="text-xl font-heading font-bold text-foreground mb-2">You're Live!</h2>
                    <p className="text-sm text-muted-foreground mb-6">Your AI phone agent is now answering calls. Head to the dashboard to monitor performance.</p>
                    <Button variant="premium" size="lg" onClick={() => navigate('/dashboard')} className="w-full">
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
