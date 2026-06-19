import { useEffect, useState, useCallback } from "react";
import { useAppSession } from "@/context/AppSessionContext";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  getAppointments, cancelAppointment, confirmAppointment,
  getAvailableSlots, getBlockedSlots, blockSlot, unblockSlot,
} from "@/lib/api";
import {
  Calendar, Clock, Phone, User, Search, X, Loader2,
  ChevronLeft, ChevronRight, Lock, Unlock, Check,
} from "lucide-react";
import { toast } from "sonner";
import { getApiErrorMessage } from "@/lib/errors";
import CreateAppointmentDialog from "./CreateAppointmentDialog";

interface Appointment {
  id: string;
  customer_name: string;
  customer_phone: string;
  customer_email?: string;
  service_name: string;
  scheduled_date: string;
  scheduled_time: string;
  duration_minutes: number;
  status: "confirmed" | "cancelled" | "completed" | "no_show" | "conflict";
  special_instructions?: string;
  created_at: string;
}

interface Slot {
  slot_time: string;
  display_time: string;
  booked: number;
  capacity: number;
  blocked: boolean;
  available: boolean;
}

interface BlockedSlot {
  id: string;
  slot_time: string;
  reason: string;
}

const statusColors: Record<string, string> = {
  confirmed:  "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
  cancelled:  "bg-red-500/10 text-red-500 border-red-500/20",
  completed:  "bg-blue-500/10 text-blue-500 border-blue-500/20",
  no_show:    "bg-amber-500/10 text-amber-500 border-amber-500/20",
  conflict:   "bg-orange-500/10 text-orange-500 border-orange-500/20",
};

const todayStr = () => new Date().toISOString().slice(0, 10);

// ── Bookings list ─────────────────────────────────────────────────────────

function AppointmentsList({ restaurantId }: { restaurantId: string }) {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  const fetchAppointments = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getAppointments(restaurantId, {
        page, limit: 20,
        status: statusFilter !== "ALL" ? statusFilter : undefined,
      });
      setAppointments(res.data.appointments || []);
      setTotalPages(res.data.pages || 1);
    } catch {
      toast.error("Failed to load appointments");
    } finally {
      setLoading(false);
    }
  }, [restaurantId, page, statusFilter]);

  useEffect(() => { fetchAppointments(); }, [fetchAppointments]);

  const handleCancel = async (apt: Appointment) => {
    if (!confirm(`Cancel appointment for ${apt.customer_name}?`)) return;
    try {
      await cancelAppointment(apt.id);
      toast.success("Appointment cancelled");
      fetchAppointments();
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to cancel"));
    }
  };

  const handleConfirm = async (apt: Appointment) => {
    try {
      await confirmAppointment(apt.id);
      toast.success("Appointment confirmed");
      fetchAppointments();
    } catch (err) {
      toast.error(getApiErrorMessage(err, "Failed to confirm"));
    }
  };

  const formatDate = (s: string) => {
    try {
      return new Date(s + "T00:00:00").toLocaleDateString("en-US", {
        weekday: "short", month: "short", day: "numeric",
      });
    } catch { return s; }
  };

  const filtered = appointments.filter((apt) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return apt.customer_name.toLowerCase().includes(q)
      || apt.customer_phone.includes(q)
      || apt.service_name.toLowerCase().includes(q);
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-soft" />
          <Input
            placeholder="Search by name, phone, or service..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[160px]"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All Statuses</SelectItem>
            <SelectItem value="confirmed">Confirmed</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="cancelled">Cancelled</SelectItem>
            <SelectItem value="no_show">No Show</SelectItem>
            <SelectItem value="conflict">Conflict</SelectItem>
          </SelectContent>
        </Select>
        <div className="ml-auto">
          <CreateAppointmentDialog restaurantId={restaurantId} onCreated={fetchAppointments} />
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-ink-soft" />
        </div>
      ) : filtered.length === 0 ? (
        <Card className="dash-card p-8 text-center">
          <Calendar className="w-12 h-12 mx-auto text-ink-soft mb-4" />
          <p className="text-ink-soft">
            {searchQuery || statusFilter !== "ALL" ? "No appointments match your filters" : "No appointments yet"}
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {filtered.map((apt) => (
            <Card key={apt.id} className="dash-card p-4">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex-1 min-w-[200px]">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`px-2 py-0.5 text-xs font-medium rounded-full border ${statusColors[apt.status] || statusColors.confirmed}`}>
                      {apt.status.charAt(0).toUpperCase() + apt.status.slice(1).replace("_", " ")}
                    </span>
                  </div>
                  <h3 className="font-semibold text-lg mb-1">{apt.service_name}</h3>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-soft">
                    <div className="flex items-center gap-1.5"><User className="w-4 h-4" /><span>{apt.customer_name}</span></div>
                    <div className="flex items-center gap-1.5"><Phone className="w-4 h-4" /><span>{apt.customer_phone}</span></div>
                  </div>
                  {apt.special_instructions && (
                    <p className="text-sm text-ink-soft mt-2 italic">"{apt.special_instructions}"</p>
                  )}
                  {apt.status === "conflict" && (
                    <p className="text-xs text-orange-500 mt-1">⚠ Double-booking detected — review manually</p>
                  )}
                </div>
                <div className="flex flex-col items-end gap-2">
                  <div className="text-right">
                    <div className="flex items-center gap-1.5 text-sm font-medium">
                      <Calendar className="w-4 h-4 text-ink-soft" />
                      <span>{formatDate(apt.scheduled_date)}</span>
                    </div>
                    <div className="flex items-center gap-1.5 text-sm text-ink-soft">
                      <Clock className="w-4 h-4" />
                      <span>{apt.scheduled_time} ({apt.duration_minutes}min)</span>
                    </div>
                  </div>
                  {apt.status === "conflict" && (
                    <Button variant="outline" size="sm" onClick={() => handleConfirm(apt)}>
                      <Check className="w-4 h-4 mr-1" />Confirm
                    </Button>
                  )}
                  {(apt.status === "confirmed" || apt.status === "conflict") && (
                    <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive" onClick={() => handleCancel(apt)}>
                      <X className="w-4 h-4 mr-1" />Cancel
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <span className="text-sm text-ink-soft">Page {page} of {totalPages}</span>
          <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}>
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      )}
    </div>
  );
}

// ── Availability tab ──────────────────────────────────────────────────────

function AvailabilityTab({ restaurantId }: { restaurantId: string }) {
  const [selectedDate, setSelectedDate] = useState(todayStr());
  const [slots, setSlots] = useState<Slot[]>([]);
  const [blockedSlots, setBlockedSlots] = useState<BlockedSlot[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionSlot, setActionSlot] = useState<string | null>(null);

  const fetchSlots = useCallback(async () => {
    setLoading(true);
    try {
      const [slotsRes, blockedRes] = await Promise.all([
        getAvailableSlots(restaurantId, selectedDate),
        getBlockedSlots(restaurantId, selectedDate),
      ]);
      setSlots(slotsRes.data.slots || []);
      setBlockedSlots(blockedRes.data.blocked_slots || []);
    } catch {
      toast.error("Failed to load availability");
    } finally {
      setLoading(false);
    }
  }, [restaurantId, selectedDate]);

  useEffect(() => { fetchSlots(); }, [fetchSlots]);

  const handleBlock = async (slot: Slot) => {
    setActionSlot(slot.slot_time);
    try {
      await blockSlot(restaurantId, { date: selectedDate, slot_time: slot.slot_time });
      toast.success(`${slot.display_time} blocked`);
      fetchSlots();
    } catch {
      toast.error("Failed to block slot");
    } finally {
      setActionSlot(null);
    }
  };

  const handleUnblock = async (slot: Slot) => {
    const doc = blockedSlots.find((b) => b.slot_time === slot.slot_time);
    if (!doc) return;
    setActionSlot(slot.slot_time);
    try {
      await unblockSlot(restaurantId, doc.id);
      toast.success(`${slot.display_time} unblocked`);
      fetchSlots();
    } catch {
      toast.error("Failed to unblock slot");
    } finally {
      setActionSlot(null);
    }
  };

  const shiftDate = (days: number) => {
    const d = new Date(selectedDate + "T00:00:00");
    d.setDate(d.getDate() + days);
    setSelectedDate(d.toISOString().slice(0, 10));
  };

  const displayDate = new Date(selectedDate + "T00:00:00").toLocaleDateString("en-US", {
    weekday: "long", month: "long", day: "numeric",
  });

  return (
    <div className="space-y-4">
      {/* Date nav */}
      <div className="flex items-center gap-3">
        <Button variant="outline" size="icon" onClick={() => shiftDate(-1)}>
          <ChevronLeft className="w-4 h-4" />
        </Button>
        <div className="flex items-center gap-2 flex-1">
          <Calendar className="w-4 h-4 text-ink-soft" />
          <span className="font-medium">{displayDate}</span>
        </div>
        <Input
          type="date"
          value={selectedDate}
          onChange={(e) => setSelectedDate(e.target.value)}
          className="w-40 h-9 rounded-lg"
        />
        <Button variant="outline" size="icon" onClick={() => shiftDate(1)}>
          <ChevronRight className="w-4 h-4" />
        </Button>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs text-ink-soft">
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />Available</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" />Booked</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block" />Blocked</span>
      </div>

      {/* Slot grid */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-ink-soft" />
        </div>
      ) : slots.length === 0 ? (
        <Card className="dash-card p-8 text-center">
          <Clock className="w-10 h-10 mx-auto text-ink-soft mb-3" />
          <p className="text-ink-soft text-sm">No slots configured for this day.</p>
          <p className="text-xs text-ink-soft mt-1">Check operating hours and slot interval in Settings → Voice & AI.</p>
        </Card>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
          {slots.map((slot) => {
            const busy = actionSlot === slot.slot_time;
            const dot = slot.blocked ? "bg-red-500" : slot.booked >= slot.capacity ? "bg-amber-500" : "bg-emerald-500";
            return (
              <Card key={slot.slot_time} className={`dash-card p-3 flex flex-col gap-2 ${slot.blocked ? "opacity-60" : ""}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className={`w-2 h-2 rounded-full ${dot}`} />
                    <span className="text-sm font-medium">{slot.display_time}</span>
                  </div>
                  <span className="text-xs text-ink-soft">{slot.booked}/{slot.capacity}</span>
                </div>
                {slot.blocked ? (
                  <Button variant="outline" size="sm" className="w-full h-7 text-xs" disabled={busy} onClick={() => handleUnblock(slot)}>
                    {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <><Unlock className="w-3 h-3 mr-1" />Unblock</>}
                  </Button>
                ) : (
                  <Button variant="outline" size="sm" className="w-full h-7 text-xs text-ink-soft" disabled={busy} onClick={() => handleBlock(slot)}>
                    {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <><Lock className="w-3 h-3 mr-1" />Block</>}
                  </Button>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Page root ─────────────────────────────────────────────────────────────

export default function AppointmentsPage() {
  const { activeRestaurant } = useAppSession();
  const restaurantId = activeRestaurant?.id ?? "";

  return (
    <div className="dash space-y-6" data-testid="appointments-page">
      <div>
        <p className="eyebrow mb-2">Schedule</p>
        <h1 className="text-2xl font-display font-bold">Appointments</h1>
        <p className="text-sm text-ink-soft mt-1">
          View appointments and manage daily availability
        </p>
      </div>

      <Tabs defaultValue="list">
        <TabsList className="bg-cream rounded-xl p-1 h-auto">
          <TabsTrigger value="list" className="rounded-lg px-4 py-2 text-sm data-[state=active]:bg-card data-[state=active]:shadow-sm">
            <User className="w-4 h-4 mr-2" />Bookings
          </TabsTrigger>
          <TabsTrigger value="availability" className="rounded-lg px-4 py-2 text-sm data-[state=active]:bg-card data-[state=active]:shadow-sm">
            <Calendar className="w-4 h-4 mr-2" />Availability
          </TabsTrigger>
        </TabsList>

        <TabsContent value="list" className="mt-4">
          <AppointmentsList restaurantId={restaurantId} />
        </TabsContent>

        <TabsContent value="availability" className="mt-4">
          <AvailabilityTab restaurantId={restaurantId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}