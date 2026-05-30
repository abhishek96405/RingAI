import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Save } from "lucide-react";
import { getBusinessLabel, getSpecialtyLabel, type FieldErrors } from "./constants";

interface Props {
  restaurant: any;
  setRestaurant: (r: any) => void;
  config: any;
  setConfig: (c: any) => void;
  businessType: string;
  isAppointmentBusiness: boolean;
  saving: boolean;
  errors: FieldErrors;
  clearError: (field: string) => void;
  onSave: () => Promise<void>;
}

const Req = () => <span className="text-destructive ml-0.5">*</span>;
const FieldError = ({ msg }: { msg?: string }) => msg ? <p className="text-xs text-destructive mt-1">{msg}</p> : null;
const errCls = (msg?: string) => msg ? "border-destructive focus-visible:ring-destructive" : "";

export default function BusinessTab({
  restaurant, setRestaurant, businessType,
  saving, errors, clearError, onSave,
}: Props) {
  const setR = (patch: any, errorKey?: string) => {
    setRestaurant({ ...restaurant, ...patch });
    if (errorKey) clearError(errorKey);
  };

  return (
    <Card className="premium-card p-6 space-y-5">
      <div>
        <h3 className="font-display font-bold text-lg mb-1">Business Details</h3>
        <p className="text-sm text-muted-foreground">
          Your {getBusinessLabel(businessType).toLowerCase()}'s identity, contact, and forwarding number.
        </p>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>{getBusinessLabel(businessType)} Name<Req /></Label>
          <Input
            value={restaurant?.name || ""}
            onChange={(e) => setR({ name: e.target.value }, "name")}
            className={`h-11 rounded-xl ${errCls(errors.name)}`}
          />
          <FieldError msg={errors.name} />
        </div>

        <div className="space-y-2">
          <Label>{getSpecialtyLabel(businessType)}</Label>
          <Input
            value={restaurant?.cuisine_type || ""}
            onChange={(e) => setRestaurant({ ...restaurant, cuisine_type: e.target.value })}
            placeholder={
              businessType === "clinic" ? "e.g. Family Medicine, Dental" :
              businessType === "salon" ? "e.g. Hair, Nails, Spa" :
              businessType === "legal" ? "e.g. Family Law, Criminal" :
              businessType === "home_services" ? "e.g. HVAC, Plumbing, Cleaning" :
              ""
            }
            className="h-11 rounded-xl"
          />
        </div>

        <div className="space-y-2"><Label>Owner Name</Label><Input value={restaurant?.owner_name || ""} onChange={(e) => setRestaurant({ ...restaurant, owner_name: e.target.value })} className="h-11 rounded-xl" /></div>
        <div className="space-y-2"><Label>Owner Email</Label><Input value={restaurant?.owner_email || ""} onChange={(e) => setRestaurant({ ...restaurant, owner_email: e.target.value })} className="h-11 rounded-xl" /></div>
        <div className="space-y-2">
          <Label>Business Phone</Label>
          <Input value={restaurant?.business_phone || ""} onChange={(e) => setRestaurant({ ...restaurant, business_phone: e.target.value })} className="h-11 rounded-xl" />
          <p className="text-xs text-muted-foreground">Set up call forwarding for this number in Settings → Phone & Forwarding.</p>
        </div>
        <div className="space-y-2"><Label>Billing Email</Label><Input value={restaurant?.billing_email || ""} onChange={(e) => setRestaurant({ ...restaurant, billing_email: e.target.value })} className="h-11 rounded-xl" /></div>

        <div className="space-y-2 sm:col-span-2">
          <Label>Street Address<Req /></Label>
          <Input
            value={restaurant?._street || ""}
            onChange={(e) => setR({ _street: e.target.value }, "_street")}
            placeholder="1520 W Ogden Ave"
            className={`h-11 rounded-xl ${errCls(errors._street)}`}
          />
          <FieldError msg={errors._street} />
        </div>

        <div className="space-y-2">
          <Label>City<Req /></Label>
          <Input
            value={restaurant?._city || ""}
            onChange={(e) => setR({ _city: e.target.value }, "_city")}
            placeholder="Naperville"
            className={`h-11 rounded-xl ${errCls(errors._city)}`}
          />
          <FieldError msg={errors._city} />
        </div>

        <div className="space-y-2">
          <Label>State<Req /></Label>
          <Input
            value={restaurant?._state || ""}
            onChange={(e) => setR({ _state: e.target.value }, "_state")}
            placeholder="IL"
            maxLength={2}
            className={`h-11 rounded-xl ${errCls(errors._state)}`}
          />
          <FieldError msg={errors._state} />
        </div>

        <div className="space-y-2">
          <Label>Zip Code<Req /></Label>
          <Input
            value={restaurant?._zip || ""}
            onChange={(e) => setR({ _zip: e.target.value }, "_zip")}
            placeholder="60540"
            maxLength={5}
            className={`h-11 rounded-xl ${errCls(errors._zip)}`}
          />
          <FieldError msg={errors._zip} />
        </div>

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

      </div>

      <Button onClick={onSave} disabled={saving} className="bg-gradient-primary text-primary-foreground rounded-xl shadow-glow hover:opacity-90">
        <Save className="w-4 h-4 mr-2" />{saving ? "Saving..." : "Save Changes"}
      </Button>
    </Card>
  );
}