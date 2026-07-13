import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Save } from "lucide-react";
import type { Dispatch, SetStateAction } from "react";
import type { Restaurant, Config } from "@/types";
import { isProPlan } from "@/lib/plan";

interface Props {
  restaurant: Restaurant | null;
  setRestaurant: Dispatch<SetStateAction<Restaurant | null>>;
  config: Config | null;
  setConfig: Dispatch<SetStateAction<Config | null>>;
  saving: boolean;
  onSave: () => Promise<void>;
}

export default function FulfillmentTab({ restaurant, setRestaurant, config, setConfig, saving, onSave }: Props) {
  return (
    <Card className="dash-card p-6 space-y-6">
      <div>
        <h3 className="font-display font-bold text-lg mb-1">Fulfillment</h3>
        <p className="text-sm text-ink-soft">How orders are fulfilled â€” pickup, delivery, reservations, and payment.</p>
      </div>

      {/* Capability toggles */}
      <div className="grid sm:grid-cols-2 gap-4">
        {[["pickup_enabled", "Pickup Enabled"], ["delivery_enabled", "Delivery Enabled"], ["reservations_enabled", "Reservations Enabled"]].map(([key, label]) => {
          const isGated = (key === "delivery_enabled" || key === "reservations_enabled") && !isProPlan(restaurant?.plan);
          return (
            <div key={key} className="flex items-center justify-between p-3 rounded-lg bg-cream">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium">{label}</p>
                {isGated && <span className="text-xs text-ink-soft">(Pro)</span>}
              </div>
              <Switch checked={restaurant?.[key] ?? false} disabled={isGated} onCheckedChange={(v) => setRestaurant({ ...restaurant, [key]: v })} />
            </div>
          );
        })}

        {[
          { key: "offers_delivery", label: "Does your restaurant offer delivery?" },
          { key: "offers_reservations", label: "Does your restaurant take reservations?" },
        ].map(({ key, label }) => (
          <div key={key} className="flex items-center justify-between p-3 rounded-lg bg-cream">
            <span className="text-sm">{label}</span>
            <div className="flex gap-2">
              <button type="button" onClick={() => setRestaurant({ ...restaurant, [key]: true })} className={`px-3 py-1 text-xs rounded-lg font-medium transition-colors ${restaurant?.[key] !== false ? "bg-coral text-white" : "bg-cream text-ink-soft"}`}>Yes</button>
              <button type="button" onClick={() => setRestaurant({ ...restaurant, [key]: false })} className={`px-3 py-1 text-xs rounded-lg font-medium transition-colors ${restaurant?.[key] === false ? "bg-coral text-white" : "bg-cream text-ink-soft"}`}>No</button>
            </div>
          </div>
        ))}
      </div>

      {/* Avg prep time */}
      <div className="grid sm:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Average Prep Time (minutes)</Label>
          <Input
            type="number"
            value={restaurant?.avg_prep_time_minutes ?? 20}
            onChange={(e) => setRestaurant({ ...restaurant, avg_prep_time_minutes: Number(e.target.value || 0) })}
            className="h-11 rounded-xl"
          />
          <p className="text-xs text-ink-soft">Used to estimate pickup and delivery ETAs.</p>
        </div>
      </div>

      {/* Reservation Settings */}
      {restaurant?.reservations_enabled && (
        <div className="space-y-4 p-4 rounded-lg border border-coral/20 bg-coral/5">
          <h4 className="font-medium text-sm">Reservation Settings</h4>
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-xs">Max Party Size</Label>
              <Input type="number" min={1} max={50} value={restaurant?.reservation_party_limit || 8}
                onChange={(e) => setRestaurant({ ...restaurant, reservation_party_limit: parseInt(e.target.value) || 8 })} className="h-9" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Max Reservations Per Slot</Label>
              <Input type="number" min={1} max={50} value={restaurant?.reservation_max_per_slot || 5}
                onChange={(e) => setRestaurant({ ...restaurant, reservation_max_per_slot: parseInt(e.target.value) || 5 })} className="h-9" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Slot Duration (minutes)</Label>
              <select value={restaurant?.reservation_slot_duration || 30}
                onChange={(e) => setRestaurant({ ...restaurant, reservation_slot_duration: parseInt(e.target.value) })}
                className="w-full h-9 rounded-lg border border-line bg-card px-3 text-sm">
                <option value={15}>15 min</option><option value={30}>30 min</option><option value={45}>45 min</option><option value={60}>60 min</option>
              </select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Advance Booking Days</Label>
              <Input type="number" min={1} max={90} value={restaurant?.reservation_advance_booking_days || 7}
                onChange={(e) => setRestaurant({ ...restaurant, reservation_advance_booking_days: parseInt(e.target.value) || 7 })} className="h-9" />
            </div>
          </div>
          <div className="flex items-center justify-between gap-3 pt-3 border-t border-coral/15">
            <div className="min-w-0">
              <p className="text-sm font-medium">Let the AI take reservations on calls</p>
              <p className="text-xs text-ink-soft">Off = you still add reservations manually here, but the AI won't book tables during phone calls.</p>
            </div>
            <Switch
              checked={restaurant?.ai_accepts_reservations !== false}
              onCheckedChange={(v) => setRestaurant({ ...restaurant, ai_accepts_reservations: v })}
            />
          </div>
        </div>
      )}

      {/* Delivery Settings */}
      {restaurant?.delivery_enabled && (
        <div className="space-y-4 p-4 rounded-lg border border-coral/20 bg-coral/5">
          <h4 className="font-medium text-sm">Delivery Settings</h4>
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-xs">Delivery Minimum ($)</Label>
              <Input type="number" value={((config?.delivery_minimum || 1500) / 100).toFixed(2)}
                onChange={(e) => setConfig({ ...config, delivery_minimum: Math.round(parseFloat(e.target.value || "0") * 100) })}
                step="0.01" min="0" className="h-9" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Delivery Fee ($)</Label>
              <Input type="number" value={((restaurant?.delivery_fee || 0) / 100).toFixed(2)}
                onChange={(e) => setRestaurant({ ...restaurant, delivery_fee: Math.round(parseFloat(e.target.value || "0") * 100) })}
                step="0.01" min="0" placeholder="0 = free delivery" className="h-9" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Delivery Radius (miles)</Label>
              <Input type="number" value={restaurant?.delivery_radius_miles || 5}
                onChange={(e) => setRestaurant({ ...restaurant, delivery_radius_miles: parseFloat(e.target.value) || 5 })}
                step="0.5" min="0.5" max="50" className="h-9" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Extra Delivery Time (min)</Label>
              <Input type="number" value={restaurant?.delivery_eta_offset_minutes || 15}
                onChange={(e) => setRestaurant({ ...restaurant, delivery_eta_offset_minutes: parseInt(e.target.value) || 15 })}
                min="0" max="60" className="h-9" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Delivery Zip Codes (comma separated)</Label>
            <Input value={(restaurant?.delivery_zip_codes || []).join(", ")}
              onChange={(e) => setRestaurant({ ...restaurant, delivery_zip_codes: e.target.value.split(",").map((z: string) => z.trim()).filter(Boolean) })}
              placeholder="60540, 60563, 60564" className="h-9" />
            <p className="text-xs text-ink-soft">AI will only accept delivery orders from these zip codes. Leave empty to accept all areas.</p>
          </div>
        </div>
      )}

      <Button onClick={onSave} disabled={saving} className="bg-coral hover:bg-coral-deep text-white rounded-xl hover:opacity-90">
        <Save className="w-4 h-4 mr-2" />{saving ? "Saving..." : "Save Fulfillment"}
      </Button>
    </Card>
  );
}