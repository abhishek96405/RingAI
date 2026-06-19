import { useState, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Plus, Loader2 } from "lucide-react";
import { getServices, getAvailableSlots, bookAppointment } from "@/lib/api";
import { toast } from "sonner";
import { getApiErrorMessage } from "@/lib/errors";

interface Service {
  id: string;
  name: string;
  duration_minutes: number;
  price_cents: number | null;
}

interface Slot {
  slot_time: string;
  display_time: string;
  available: boolean;
}

const todayStr = () => new Date().toISOString().slice(0, 10);

const emptyForm = {
  service_id: "",
  service_name: "",
  scheduled_date: todayStr(),
  scheduled_time: "",
  customer_name: "",
  customer_phone: "",
  customer_email: "",
  special_instructions: "",
};

// Manual appointment entry — parity with the reservations create flow (C17-4).
// Wired to the existing bookAppointment endpoint, which persists to
// db.appointments regardless of Google Calendar state and sends the same
// confirmation SMS a voice booking would.
export default function CreateAppointmentDialog({
  restaurantId,
  onCreated,
}: {
  restaurantId: string;
  onCreated: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [services, setServices] = useState<Service[]>([]);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({ ...emptyForm });

  // Load services when the dialog opens.
  useEffect(() => {
    if (!open || !restaurantId) return;
    getServices(restaurantId)
      .then((res) => setServices(res.data || []))
      .catch(() => toast.error("Failed to load services"));
  }, [open, restaurantId]);

  // Refresh available slots whenever the chosen date or service changes —
  // service duration affects which slots fit.
  const loadSlots = useCallback(async () => {
    if (!open || !restaurantId || !form.scheduled_date) return;
    setSlotsLoading(true);
    try {
      const res = await getAvailableSlots(
        restaurantId,
        form.scheduled_date,
        form.service_name || undefined
      );
      setSlots(res.data.slots || []);
    } catch {
      setSlots([]);
    } finally {
      setSlotsLoading(false);
    }
  }, [open, restaurantId, form.scheduled_date, form.service_name]);

  useEffect(() => { loadSlots(); }, [loadSlots]);

  const handleServiceChange = (serviceId: string) => {
    const svc = services.find((s) => s.id === serviceId);
    // Service change can invalidate the chosen time — clear it so the operator re-picks.
    setForm((f) => ({
      ...f,
      service_id: serviceId,
      service_name: svc?.name || "",
      scheduled_time: "",
    }));
  };

  const handleCreate = async () => {
    if (!form.service_name || !form.scheduled_time || !form.customer_name || !form.customer_phone) {
      toast.error("Service, time, name, and phone are required");
      return;
    }
    setSubmitting(true);
    try {
      await bookAppointment(restaurantId, {
        service_name: form.service_name,
        service_id: form.service_id || undefined,
        scheduled_date: form.scheduled_date,
        scheduled_time: form.scheduled_time,
        customer_name: form.customer_name,
        customer_phone: form.customer_phone,
        customer_email: form.customer_email || undefined,
        special_instructions: form.special_instructions || undefined,
      });
      toast.success("Appointment booked");
      setOpen(false);
      setForm({ ...emptyForm });
      onCreated();
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to book appointment"));
    } finally {
      setSubmitting(false);
    }
  };

  const availableSlots = slots.filter((s) => s.available);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button data-testid="create-appointment-btn">
          <Plus className="w-4 h-4 mr-2" /> New Appointment
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Book Appointment</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 mt-4">
          <div>
            <Label>Service *</Label>
            <Select value={form.service_id} onValueChange={handleServiceChange}>
              <SelectTrigger data-testid="appointment-service">
                <SelectValue placeholder="Select a service" />
              </SelectTrigger>
              <SelectContent>
                {services.map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.name} ({s.duration_minutes} min)
                  </SelectItem>
                ))}
                {services.length === 0 && (
                  <div className="p-2 text-sm text-ink-soft">No services configured</div>
                )}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label htmlFor="appt_date">Date *</Label>
              <Input
                id="appt_date"
                type="date"
                value={form.scheduled_date}
                onChange={(e) => setForm({ ...form, scheduled_date: e.target.value, scheduled_time: "" })}
              />
            </div>
            <div>
              <Label>Time *</Label>
              <Select
                value={form.scheduled_time}
                onValueChange={(v) => setForm({ ...form, scheduled_time: v })}
              >
                <SelectTrigger data-testid="appointment-time">
                  <SelectValue placeholder={slotsLoading ? "Loading..." : "Select time"} />
                </SelectTrigger>
                <SelectContent>
                  {availableSlots.map((slot) => (
                    <SelectItem key={slot.slot_time} value={slot.display_time}>
                      {slot.display_time}
                    </SelectItem>
                  ))}
                  {!slotsLoading && availableSlots.length === 0 && (
                    <div className="p-2 text-sm text-ink-soft">No available slots</div>
                  )}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <Label htmlFor="appt_name">Customer Name *</Label>
            <Input
              id="appt_name"
              data-testid="appointment-customer-name"
              value={form.customer_name}
              onChange={(e) => setForm({ ...form, customer_name: e.target.value })}
              placeholder="Jane Doe"
            />
          </div>
          <div>
            <Label htmlFor="appt_phone">Phone *</Label>
            <Input
              id="appt_phone"
              data-testid="appointment-customer-phone"
              value={form.customer_phone}
              onChange={(e) => setForm({ ...form, customer_phone: e.target.value })}
              placeholder="+1 555-123-4567"
            />
          </div>
          <div>
            <Label htmlFor="appt_email">Email</Label>
            <Input
              id="appt_email"
              type="email"
              value={form.customer_email}
              onChange={(e) => setForm({ ...form, customer_email: e.target.value })}
              placeholder="jane@example.com"
            />
          </div>
          <div>
            <Label htmlFor="appt_notes">Special Instructions</Label>
            <Input
              id="appt_notes"
              value={form.special_instructions}
              onChange={(e) => setForm({ ...form, special_instructions: e.target.value })}
              placeholder="Allergies, preferences, etc."
            />
          </div>

          <Button
            onClick={handleCreate}
            className="w-full"
            disabled={submitting}
            data-testid="submit-appointment-btn"
          >
            {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : "Book Appointment"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
