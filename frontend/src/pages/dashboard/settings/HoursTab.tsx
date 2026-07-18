import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Save, X } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import type { Config, DayHours } from "@/types";
import { days, defaultHours, normalizeDayHours, type NormalizedDayHours } from "./constants";

interface Props {
  config: Config | null;
  setConfig: Dispatch<SetStateAction<Config | null>>;
  saving: boolean;
  onSave: () => Promise<void>;
}

type DayKey = keyof typeof defaultHours;

export default function HoursTab({ config, setConfig, saving, onSave }: Props) {
  // Every write emits the NEW canonical shape ({closed, last_call_offset_minutes,
  // periods}). The backend also reads the old {open,close} shape, so mixing old
  // stored configs with new writes is safe.
  const writeDay = (dayKey: DayKey, next: NormalizedDayHours) => {
    const dayValue: DayHours = {
      closed: next.closed,
      last_call_offset_minutes: next.last_call_offset_minutes,
      periods: next.periods,
    };
    setConfig({
      ...config,
      operating_hours: { ...config?.operating_hours, [dayKey]: dayValue },
    });
  };

  const setClosed = (dayKey: DayKey, day: NormalizedDayHours, closed: boolean) =>
    writeDay(dayKey, { ...day, closed });

  const setOffset = (dayKey: DayKey, day: NormalizedDayHours, value: string) => {
    const n = parseInt(value, 10);
    writeDay(dayKey, { ...day, last_call_offset_minutes: Number.isFinite(n) && n > 0 ? n : 0 });
  };

  const setPeriodField = (
    dayKey: DayKey,
    day: NormalizedDayHours,
    index: number,
    field: "open" | "close",
    value: string,
  ) => {
    const periods = day.periods.map((p, i) => (i === index ? { ...p, [field]: value } : p));
    writeDay(dayKey, { ...day, periods });
  };

  const addPeriod = (dayKey: DayKey, day: NormalizedDayHours) => {
    // Seed the new period just after the last one so owners rarely retype both.
    const last = day.periods[day.periods.length - 1];
    const seed = last ? { open: last.close, close: last.close } : { open: "09:00", close: "17:00" };
    writeDay(dayKey, { ...day, periods: [...day.periods, seed] });
  };

  const removePeriod = (dayKey: DayKey, day: NormalizedDayHours, index: number) => {
    const periods = day.periods.filter((_, i) => i !== index);
    // Never leave a non-closed day with zero periods — keep at least one.
    writeDay(dayKey, { ...day, periods: periods.length ? periods : [{ open: "09:00", close: "17:00" }] });
  };

  return (
    <Card className="dash-card p-6 space-y-6">
      <div>
        <h3 className="font-display font-bold text-lg mb-1">Hours & Availability</h3>
        <p className="text-sm text-ink-soft">When you're open, and what the AI does when you're not.</p>
      </div>

      <div>
        <Label className="mb-3 block">Operating Hours</Label>
        <p className="text-xs text-ink-soft mb-3">
          Add multiple time ranges for a day with a midday break (e.g. lunch and dinner). "Last call"
          is how many minutes before closing the AI stops taking orders — it applies to every range that day.
        </p>
        <div className="space-y-2">
          {days.map(([key, label]) => {
            const day = normalizeDayHours(config?.operating_hours?.[key] ?? defaultHours[key]);
            return (
              <div key={key} className="p-3 rounded-lg bg-cream/20 space-y-2">
                <div className="grid grid-cols-12 gap-2 items-center">
                  <div className="col-span-3"><p className="text-sm font-medium">{label}</p></div>
                  <div className="col-span-3 flex items-center gap-2">
                    <input
                      type="checkbox"
                      className="accent-coral"
                      checked={day.closed}
                      onChange={(e) => setClosed(key, day, e.target.checked)}
                    />
                    <span className="text-xs text-ink-soft">Closed</span>
                  </div>
                  {!day.closed && (
                    <div className="col-span-6 flex items-center justify-end gap-2">
                      <span className="text-xs text-ink-soft whitespace-nowrap">Last call (min)</span>
                      <Input
                        type="number"
                        min={0}
                        className="w-20"
                        aria-label={`${label} last call offset in minutes`}
                        value={day.last_call_offset_minutes}
                        onChange={(e) => setOffset(key, day, e.target.value)}
                      />
                    </div>
                  )}
                </div>

                {!day.closed && (
                  <div className="space-y-2">
                    {day.periods.map((p, idx) => (
                      <div key={idx} className="grid grid-cols-12 gap-2 items-center">
                        <div className="col-span-1" />
                        <div className="col-span-4">
                          <Input
                            type="time"
                            aria-label={`${label} period ${idx + 1} open`}
                            value={p.open}
                            onChange={(e) => setPeriodField(key, day, idx, "open", e.target.value)}
                          />
                        </div>
                        <div className="col-span-1 text-center text-xs text-ink-soft">to</div>
                        <div className="col-span-4">
                          <Input
                            type="time"
                            aria-label={`${label} period ${idx + 1} close`}
                            value={p.close}
                            onChange={(e) => setPeriodField(key, day, idx, "close", e.target.value)}
                          />
                        </div>
                        <div className="col-span-2 flex justify-end">
                          {day.periods.length > 1 && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              aria-label={`Remove ${label} period ${idx + 1}`}
                              onClick={() => removePeriod(key, day, idx)}
                            >
                              <X className="w-4 h-4" />
                            </Button>
                          )}
                        </div>
                      </div>
                    ))}
                    <div className="grid grid-cols-12">
                      <div className="col-span-1" />
                      <button
                        type="button"
                        className="col-span-11 inline-flex items-center gap-1 text-xs text-coral hover:text-coral-deep w-fit"
                        onClick={() => addPeriod(key, day)}
                      >
                        <Plus className="w-3 h-3" /> Add time range
                      </button>
                    </div>
                  </div>
                )}
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
