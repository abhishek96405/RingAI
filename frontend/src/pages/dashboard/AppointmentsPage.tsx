import { useEffect, useState } from "react";
import { useAppSession } from "@/context/AppSessionContext";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getAppointments, cancelAppointment } from "@/lib/api";
import {
  Calendar,
  Clock,
  Phone,
  User,
  Search,
  X,
  Loader2,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { toast } from "sonner";

interface Appointment {
  id: string;
  customer_name: string;
  customer_phone: string;
  customer_email?: string;
  service_name: string;
  scheduled_date: string;
  scheduled_time: string;
  duration_minutes: number;
  status: "confirmed" | "cancelled" | "completed" | "no_show";
  special_instructions?: string;
  created_at: string;
}

const statusColors: Record<string, string> = {
  confirmed: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
  cancelled: "bg-red-500/10 text-red-500 border-red-500/20",
  completed: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  no_show: "bg-amber-500/10 text-amber-500 border-amber-500/20",
};

export default function AppointmentsPage() {
  const { activeRestaurant } = useAppSession();
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  const fetchAppointments = async () => {
    if (!activeRestaurant?.id) return;
    setLoading(true);
    try {
      const res = await getAppointments(activeRestaurant.id, {
        page,
        limit: 20,
        status: statusFilter !== "ALL" ? statusFilter : undefined,
      });
      setAppointments(res.data.appointments || []);
      setTotalPages(res.data.pages || 1);
    } catch (err) {
      console.error("Failed to fetch appointments", err);
      toast.error("Failed to load appointments");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAppointments();
  }, [activeRestaurant?.id, page, statusFilter]);

  const handleCancel = async (appointment: Appointment) => {
    if (!confirm(`Cancel appointment for ${appointment.customer_name}?`)) return;
    try {
      await cancelAppointment(appointment.id);
      toast.success("Appointment cancelled");
      fetchAppointments();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to cancel appointment");
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
      });
    } catch {
      return dateStr;
    }
  };

  const filteredAppointments = appointments.filter((apt) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      apt.customer_name.toLowerCase().includes(query) ||
      apt.customer_phone.includes(query) ||
      apt.service_name.toLowerCase().includes(query)
    );
  });

  return (
    <div className="space-y-6" data-testid="appointments-page">
      <div>
        <h1 className="text-2xl font-display font-bold">Appointments</h1>
        <p className="text-sm text-muted-foreground mt-1">
          View and manage all booked appointments
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search by name, phone, or service..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
            data-testid="appointments-search"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[160px]" data-testid="status-filter">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All Statuses</SelectItem>
            <SelectItem value="confirmed">Confirmed</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="cancelled">Cancelled</SelectItem>
            <SelectItem value="no_show">No Show</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Appointments List */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : filteredAppointments.length === 0 ? (
        <Card className="p-8 text-center">
          <Calendar className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
          <p className="text-muted-foreground">
            {searchQuery || statusFilter !== "ALL"
              ? "No appointments match your filters"
              : "No appointments yet"}
          </p>
        </Card>
      ) : (
        <div className="space-y-3">
          {filteredAppointments.map((apt) => (
            <Card
              key={apt.id}
              className="p-4"
              data-testid={`appointment-card-${apt.id}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex-1 min-w-[200px]">
                  <div className="flex items-center gap-2 mb-2">
                    <span
                      className={`px-2 py-0.5 text-xs font-medium rounded-full border ${
                        statusColors[apt.status] || statusColors.confirmed
                      }`}
                    >
                      {apt.status.charAt(0).toUpperCase() + apt.status.slice(1)}
                    </span>
                  </div>

                  <h3 className="font-semibold text-lg mb-1">{apt.service_name}</h3>

                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                    <div className="flex items-center gap-1.5">
                      <User className="w-4 h-4" />
                      <span>{apt.customer_name}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Phone className="w-4 h-4" />
                      <span>{apt.customer_phone}</span>
                    </div>
                  </div>

                  {apt.special_instructions && (
                    <p className="text-sm text-muted-foreground mt-2 italic">
                      "{apt.special_instructions}"
                    </p>
                  )}
                </div>

                <div className="flex flex-col items-end gap-2">
                  <div className="text-right">
                    <div className="flex items-center gap-1.5 text-sm font-medium">
                      <Calendar className="w-4 h-4 text-muted-foreground" />
                      <span>{formatDate(apt.scheduled_date)}</span>
                    </div>
                    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      <Clock className="w-4 h-4" />
                      <span>
                        {apt.scheduled_time} ({apt.duration_minutes}min)
                      </span>
                    </div>
                  </div>

                  {apt.status === "confirmed" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:text-destructive"
                      onClick={() => handleCancel(apt)}
                      data-testid={`cancel-appointment-${apt.id}`}
                    >
                      <X className="w-4 h-4 mr-1" />
                      Cancel
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            <ChevronLeft className="w-4 h-4" />
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
          >
            <ChevronRight className="w-4 h-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
