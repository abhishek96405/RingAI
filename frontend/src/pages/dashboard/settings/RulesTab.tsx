import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { AlertTriangle, Plus, Save, ShieldAlert, X } from "lucide-react";

interface Props {
  config: any;
  setConfig: (c: any) => void;
  saving: boolean;
  onSave: () => Promise<void>;
}

export default function RulesTab({ config, setConfig, saving, onSave }: Props) {
  const [newRule, setNewRule] = useState("");
  const [newEscalation, setNewEscalation] = useState("");

  const addRule = () => {
    if (!newRule.trim()) return;
    setConfig({ ...config, business_rules: [...(config?.business_rules || []), newRule.trim()] });
    setNewRule("");
  };
  const removeRule = (i: number) =>
    setConfig({ ...config, business_rules: (config?.business_rules || []).filter((_: unknown, idx: number) => idx !== i) });
  const addEscalation = () => {
    if (!newEscalation.trim()) return;
    setConfig({ ...config, escalation_rules: [...(config?.escalation_rules || []), newEscalation.trim()] });
    setNewEscalation("");
  };
  const removeEscalation = (i: number) =>
    setConfig({ ...config, escalation_rules: (config?.escalation_rules || []).filter((_: unknown, idx: number) => idx !== i) });

  return (
    <div className="space-y-4">
      <Card className="dash-card p-6 space-y-4">
        <div>
          <h3 className="font-display font-bold text-lg mb-1">Business Rules</h3>
          <p className="text-sm text-ink-soft">Rules the AI will follow when handling calls.</p>
        </div>
        <div className="space-y-2">
          {(config?.business_rules || []).map((rule: string, i: number) => (
            <div key={i} className="flex items-center gap-2 p-2.5 rounded-lg bg-cream">
              <span className="text-xs text-ink-soft w-5">{i + 1}.</span>
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

      <Card className="dash-card p-6 space-y-4">
        <div>
          <h3 className="font-display font-bold text-lg mb-1 flex items-center gap-2"><ShieldAlert className="w-4 h-4" />Escalation Triggers</h3>
          <p className="text-sm text-ink-soft">Situations where the AI should transfer to a human.</p>
        </div>
        <div className="space-y-2">
          {(config?.escalation_rules || []).map((rule: string, i: number) => (
            <div key={i} className="flex items-center gap-2 p-2.5 rounded-lg bg-honey/5">
              <AlertTriangle className="w-3.5 h-3.5 text-[#a26d0d] shrink-0" />
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

      <Button onClick={onSave} disabled={saving} className="bg-coral hover:bg-coral-deep text-white rounded-xl hover:opacity-90">
        <Save className="w-4 h-4 mr-2" />{saving ? "Saving..." : "Save Rules"}
      </Button>
    </div>
  );
}