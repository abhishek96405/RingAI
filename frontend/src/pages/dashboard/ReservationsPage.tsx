import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { useAppSession } from "@/context/AppSessionContext";
import { useSearchParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CalendarIcon, Users, Clock, X, Plus, Phone, Mail } from "lucide-react";
import { api, getRestaurantId } from "@/lib/api";
import { format } from "date-fns";
import { isProPlan } from "@/lib/plan";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface Reservation {
  id: string;
  customer_name: string;
  customer_phone: string;
  customer_email?: string;
  party_size: number;
  reservation_date: string;
  reservation_time: string;
  special_requests?: string;
  status: string;
  created_at: string;
}

interface TimeSlot {
  time: string;
  display_time: string;
  available: boolean;
  remaining_capacity: number;
  total_capacity: number;
  blocked: boolean;
}

const statusColors: Record<string, string> = {
  confirmed: "bg-green-500",
  pending: "bg-yellow-500",
  cancelled: "bg-red-500",
  no_show: "bg-gray-500",
  completed: "bg-blue-500",
};

export const ReservationsPage = () => {
  const { activeRestaurant } = useAppSession();
  const isPro = isProPlan(activeRestaurant?.plan);

  const [searchParams] = useSearchParams();
  const restaurantId = searchParams.get("restaurant_id") || getRestaurantId() || "";

  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDate, setSelectedDate] = useState<Date>(new Date());
  const [slots, setSlots] = useState<TimeSlot[]>([]);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // New reservation form
  const [formData, setFormData] = useState({
    customer_name: "",
    customer_phone: "",
    customer_email: "",
    party_size: 2,
    reservation_time: "",
    special_requests: "",
  });

  const fetchReservations = useCallback(async () => {
    try {
      setLoading(true);
      const dateStr = format(selectedDate, "yyyy-MM-dd");
      const params: Record<string, unknown> = { date: dateStr };
      if (statusFilter !== "all") {
        params.status = statusFilter;
      }
      const res = await api.get(`/restaurants/${restaurantId}/reservations`, { params });
      setReservations(res.data.reservations || []);
    } catch (err) {
      console.error("Failed to fetch reservations", err);
      toast.error("Failed to load reservations");
    } finally {
      setLoading(false);
    }
  }, [restaurantId, selectedDate, statusFilter]);

  const fetchSlots = useCallback(async () => {
    try {
      const dateStr = format(selectedDate, "yyyy-MM-dd");
      const res = await api.get(`/restaurants/${restaurantId}/reservation-slots`, {
        params: { date: dateStr },
      });
      setSlots(res.data.slots || []);
    } catch (err) {
      console.error("Failed to fetch slots", err);
    }
  }, [restaurantId, selectedDate]);

  useEffect(() => {
    if (isPro && restaurantId) {
      fetchReservations();
      fetchSlots();
    }
  }, [isPro, restaurantId, fetchReservations, fetchSlots]);

  const handleCreate = async () => {
    if (!formData.customer_name || !formData.customer_phone || !formData.reservation_time) {
      toast.error("Please fill in all required fields");
      return;
    }

    try {
      await api.post(`/restaurants/${restaurantId}/reservations`, {
        ...formData,
        reservation_date: format(selectedDate, "yyyy-MM-dd"),
      });
      toast.success("Reservation created!");
      setIsCreateOpen(false);
      setFormData({
        customer_name: "",
        customer_phone: "",
        customer_email: "",
        party_size: 2,
        reservation_time: "",
        special_requests: "",
      });
      fetchReservations();
      fetchSlots();
    } catch (err) {
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
      toast.error(detail || "Failed to create reservation");
    }
  };

  const handleCancel = async (id: string) => {
    try {
      await api.patch(`/reservations/${id}/cancel`);
      toast.success("Reservation cancelled");
      fetchReservations();
      fetchSlots();
    } catch (err) {
      toast.error("Failed to cancel reservation");
    }
  };

  const handleConfirm = async (id: string) => {
    try {
      await api.patch(`/reservations/${id}/confirm`);
      toast.success("Reservation confirmed");
      fetchReservations();
    } catch (err) {
      toast.error("Failed to confirm reservation");
    }
  };

  const formatTime = (time: string) => {
    try {
      const [hours, minutes] = time.split(":");
      const h = parseInt(hours);
      const ampm = h >= 12 ? "PM" : "AM";
      const displayH = h > 12 ? h - 12 : h === 0 ? 12 : h;
      return `${displayH}:${minutes} ${ampm}`;
    } catch {
      return time;
    }
  };

  if (!isPro) {
    return (
      <div className="dash flex items-center justify-center py-20">
        <div className="dash-card p-8 text-center max-w-md">
          <div className="w-10 h-10 rounded-xl bg-coral/10 flex items-center justify-center mx-auto mb-4">
            <CalendarIcon className="w-5 h-5 text-coral" />
          </div>
          <h3 className="font-display font-bold text-lg mb-2">AI Table Reservations</h3>
          <p className="text-sm text-ink-soft mb-4">
            Let your AI handle table reservations, manage availability, and book parties automatically.
          </p>
          <a href="/dashboard/billing" className="inline-flex items-center justify-center rounded-xl bg-coral text-white px-6 py-2 text-sm font-medium hover:bg-coral-deep">
            Upgrade to Pro
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="dash p-6 space-y-6" data-testid="reservations-page">
      <div className="flex items-center justify-between">
        <div>
          <p className="eyebrow mb-2">Bookings</p>
          <h1 className="text-2xl font-display font-bold">Reservations</h1>
          <p className="text-ink-soft">
            Manage table reservations for {format(selectedDate, "MMMM d, yyyy")}
          </p>
        </div>
        <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
          <DialogTrigger asChild>
            <Button data-testid="create-reservation-btn" className="bg-coral hover:bg-coral-deep text-white">
              <Plus className="w-4 h-4 mr-2" /> New Reservation
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Create Reservation</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 mt-4">
              <div>
                <Label htmlFor="customer_name">Customer Name *</Label>
                <Input
                  id="customer_name"
                  data-testid="reservation-customer-name"
                  value={formData.customer_name}
                  onChange={(e) => setFormData({ ...formData, customer_name: e.target.value })}
                  placeholder="John Doe"
                />
              </div>
              <div>
                <Label htmlFor="customer_phone">Phone *</Label>
                <Input
                  id="customer_phone"
                  data-testid="reservation-customer-phone"
                  value={formData.customer_phone}
                  onChange={(e) => setFormData({ ...formData, customer_phone: e.target.value })}
                  placeholder="+1 555-123-4567"
                />
              </div>
              <div>
                <Label htmlFor="customer_email">Email</Label>
                <Input
                  id="customer_email"
                  data-testid="reservation-customer-email"
                  type="email"
                  value={formData.customer_email}
                  onChange={(e) => setFormData({ ...formData, customer_email: e.target.value })}
                  placeholder="john@example.com"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="party_size">Party Size</Label>
                  <Select
                    value={formData.party_size.toString()}
                    onValueChange={(v) => setFormData({ ...formData, party_size: parseInt(v) })}
                  >
                    <SelectTrigger data-testid="reservation-party-size">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
                        <SelectItem key={n} value={n.toString()}>
                          {n} {n === 1 ? "guest" : "guests"}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="reservation_time">Time *</Label>
                  <Select
                    value={formData.reservation_time}
                    onValueChange={(v) => setFormData({ ...formData, reservation_time: v })}
                  >
                    <SelectTrigger data-testid="reservation-time">
                      <SelectValue placeholder="Select time" />
                    </SelectTrigger>
                    <SelectContent>
                      {slots.filter((s) => s.available).map((slot) => (
                        <SelectItem key={slot.time} value={slot.time}>
                          {slot.display_time} ({slot.remaining_capacity} left)
                        </SelectItem>
                      ))}
                      {slots.filter((s) => s.available).length === 0 && (
                        <div className="p-2 text-sm text-ink-soft">No available slots</div>
                      )}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div>
                <Label htmlFor="special_requests">Special Requests</Label>
                <Input
                  id="special_requests"
                  data-testid="reservation-special-requests"
                  value={formData.special_requests}
                  onChange={(e) => setFormData({ ...formData, special_requests: e.target.value })}
                  placeholder="Birthday, allergies, etc."
                />
              </div>
              <Button onClick={handleCreate} className="w-full bg-coral hover:bg-coral-deep text-white" data-testid="submit-reservation-btn">
                Create Reservation
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Calendar */}
        <Card className="dash-card lg:col-span-1">
          <CardHeader>
            <CardTitle className="text-lg">Select Date</CardTitle>
          </CardHeader>
          <CardContent className="p-3">
            <Calendar
              mode="single"
              selected={selectedDate}
              onSelect={(d) => d && setSelectedDate(d)}
              className="rounded-md border w-full"
            />
            <div className="mt-4">
              <Label>Filter by Status</Label>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger data-testid="status-filter">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="confirmed">Confirmed</SelectItem>
                  <SelectItem value="pending">Pending</SelectItem>
                  <SelectItem value="cancelled">Cancelled</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* Reservations List */}
        <Card className="dash-card lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <CalendarIcon className="w-5 h-5" />
              Reservations for {format(selectedDate, "MMM d")}
              <Badge variant="outline">{reservations.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="text-center py-8 text-ink-soft">Loading...</div>
            ) : reservations.length === 0 ? (
              <div className="text-center py-8 text-ink-soft">
                No reservations for this date
              </div>
            ) : (
              <div className="space-y-3">
                {reservations.map((res) => (
                  <div
                    key={res.id}
                    data-testid={`reservation-${res.id}`}
                    className="p-4 border border-line rounded-lg hover:bg-cream transition-colors"
                  >
                    <div className="flex items-start justify-between">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold">{res.customer_name}</span>
                          <Badge className={cn("text-white", statusColors[res.status])}>
                            {res.status}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-4 text-sm text-ink-soft">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {formatTime(res.reservation_time)}
                          </span>
                          <span className="flex items-center gap-1">
                            <Users className="w-3 h-3" />
                            {res.party_size} guests
                          </span>
                          <span className="flex items-center gap-1">
                            <Phone className="w-3 h-3" />
                            {res.customer_phone}
                          </span>
                        </div>
                        {res.special_requests && (
                          <p className="text-sm text-ink-soft italic">
                            "{res.special_requests}"
                          </p>
                        )}
                      </div>
                      <div className="flex gap-2">
                        {res.status === "pending" && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleConfirm(res.id)}
                            data-testid={`confirm-${res.id}`}
                          >
                            Confirm
                          </Button>
                        )}
                        {(res.status === "confirmed" || res.status === "pending") && (
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => handleCancel(res.id)}
                            data-testid={`cancel-${res.id}`}
                          >
                            <X className="w-4 h-4" />
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Available Slots Overview */}
      <Card className="dash-card">
        <CardHeader>
          <CardTitle className="text-lg">Available Time Slots</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {slots.map((slot) => (
              <Badge
                key={slot.time}
                variant="outline"
                className={cn(
                  "px-3 py-1",
                  slot.blocked
                    ? "border-red-300 text-red-400 opacity-60 line-through"
                    : slot.available
                    ? "border-green-500 text-green-700"
                    : "border-gray-300 text-gray-400 opacity-50"
                )}
              >
                {slot.display_time}
                {slot.blocked
                  ? " (blocked)"
                  : slot.available
                  ? ` (${slot.remaining_capacity}/${slot.total_capacity})`
                  : " (full)"}
              </Badge>
            ))}
            {slots.length === 0 && (
              <span className="text-ink-soft">No slots configured</span>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default ReservationsPage;
