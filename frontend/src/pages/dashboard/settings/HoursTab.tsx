import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Save } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import type { Config } from "@/types";
import { days, defaultHours } from "./constants";

interface Props {
  config: Config | null;
  setConfig: Dispatch<SetStateAction<Config | null>>;
  saving: boolean;
  onSave: () => Promise<void>;
}

export default function HoursTab({ config, setConfig, saving, onSave }: Props) {
  const updateHours = (dayKey: keyof typeof defaultHours, field: string, value: string | boolean) =>
    setConfig({ ...config, operating_hours: { ...config.operating_hours, [dayKey]: { ...config.operating_hours[dayKey], [field]: value } } });

  return (
    <Card className="dash-card p-6 space-y-6">
      <div>
        <h3 className="font-display font-bold text-lg mb-1">Hours & Availability</h3>
        <p className="text-sm text-ink-soft">When you're open, and what the AI does when you're not.</p>
      </div>

      <div>
        <Label className="mb-3 block">Operating Hours</Label>
        <div className="space-y-2">
          {days.map(([key, label]) => {
            const day = config?.operating_hours?.[key] || defaultHours[key];
            return (
              <div key={key} className="grid grid-cols-12 gap-2 items-center p-3 rounded-lg bg-cream/20">
                <div className="col-span-3"><p className="text-sm font-medium">{label}</p></div>
                <div className="col-span-2 flex items-center gap-2">
                  <input type="checkbox" className="accent-coral" checked={day.closed} onChange={(e) => updateHours(key, "closed", e.target.checked)} />
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
        <p className="text-xs text-ink-soft">
          What the AI does when a call comes in outside operating hours. "Forward" uses the Escalation Phone Number from the Business tab.
        </p>
      </div>

      <Button onClick={onSave} disabled={saving} className="bg-coral hover:bg-coral-deep text-white rounded-xl hover:opacity-90">
        <Save className="w-4 h-4 mr-2" />{saving ? "Saving..." : "Save Hours"}
      </Button>
    </Card>
  );
}