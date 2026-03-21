import { useEffect, useState } from "react";
import { useAppSession } from "@/context/AppSessionContext";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  getServices,
  createService,
  updateService,
  deleteService,
} from "@/lib/api";
import { Plus, Pencil, Trash2, Clock, DollarSign, Loader2 } from "lucide-react";
import { toast } from "sonner";

interface ServiceItem {
  id: string;
  name: string;
  duration_minutes: number;
  buffer_minutes: number;
  price_cents: number | null;
  description: string | null;
  available: boolean;
  created_at: string;
}

export default function ServicesPage() {
  const { activeRestaurant } = useAppSession();
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<ServiceItem | null>(null);
  const [saving, setSaving] = useState(false);

  const [formData, setFormData] = useState({
    name: "",
    duration_minutes: 60,
    buffer_minutes: 15,
    price_cents: 0,
    description: "",
    available: true,
  });

  const fetchServices = async () => {
    if (!activeRestaurant?.id) return;
    setLoading(true);
    try {
      const res = await getServices(activeRestaurant.id);
      setServices(res.data || []);
    } catch (err) {
      console.error("Failed to fetch services", err);
      toast.error("Failed to load services");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchServices();
  }, [activeRestaurant?.id]);

  const openCreateDialog = () => {
    setEditing(null);
    setFormData({
      name: "",
      duration_minutes: 60,
      buffer_minutes: 15,
      price_cents: 0,
      description: "",
      available: true,
    });
    setDialogOpen(true);
  };

  const openEditDialog = (service: ServiceItem) => {
    setEditing(service);
    setFormData({
      name: service.name,
      duration_minutes: service.duration_minutes,
      buffer_minutes: service.buffer_minutes,
      price_cents: service.price_cents || 0,
      description: service.description || "",
      available: service.available,
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    if (!formData.name.trim()) {
      toast.error("Service name is required");
      return;
    }

    setSaving(true);
    try {
      if (editing) {
        await updateService(editing.id, formData);
        toast.success("Service updated");
      } else {
        await createService(activeRestaurant?.id, formData);
        toast.success("Service created");
      }
      setDialogOpen(false);
      fetchServices();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to save service");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (service: ServiceItem) => {
    if (!confirm(`Delete "${service.name}"?`)) return;
    try {
      await deleteService(service.id);
      toast.success("Service deleted");
      fetchServices();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to delete service");
    }
  };

  const formatPrice = (cents: number | null) => {
    if (!cents) return "—";
    return `$${(cents / 100).toFixed(2)}`;
  };

  const formatDuration = (minutes: number) => {
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return mins ? `${hours}h ${mins}m` : `${hours}h`;
  };

  return (
    <div className="space-y-6" data-testid="services-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-bold">Services</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage the services you offer for appointment booking
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button onClick={openCreateDialog} data-testid="add-service-btn">
              <Plus className="w-4 h-4 mr-2" />
              Add Service
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>{editing ? "Edit Service" : "Add Service"}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 mt-4">
              <div className="space-y-2">
                <Label>Service Name *</Label>
                <Input
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g. Haircut, Consultation, etc."
                  data-testid="service-name-input"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Duration (minutes)</Label>
                  <Input
                    type="number"
                    value={formData.duration_minutes}
                    onChange={(e) => setFormData({ ...formData, duration_minutes: Number(e.target.value) || 0 })}
                    min={5}
                    step={5}
                    data-testid="service-duration-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Buffer Time (minutes)</Label>
                  <Input
                    type="number"
                    value={formData.buffer_minutes}
                    onChange={(e) => setFormData({ ...formData, buffer_minutes: Number(e.target.value) || 0 })}
                    min={0}
                    step={5}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label>Price (optional)</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$</span>
                  <Input
                    type="number"
                    value={formData.price_cents ? (formData.price_cents / 100).toFixed(2) : ""}
                    onChange={(e) => setFormData({ ...formData, price_cents: Math.round(Number(e.target.value || 0) * 100) })}
                    className="pl-7"
                    placeholder="0.00"
                    step="0.01"
                    data-testid="service-price-input"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label>Description</Label>
                <Textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Brief description of the service..."
                  rows={2}
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="service-available"
                  checked={formData.available}
                  onChange={(e) => setFormData({ ...formData, available: e.target.checked })}
                  className="accent-primary"
                />
                <Label htmlFor="service-available" className="cursor-pointer">
                  Available for booking
                </Label>
              </div>

              <div className="flex justify-end gap-2 pt-4">
                <Button variant="outline" onClick={() => setDialogOpen(false)}>
                  Cancel
                </Button>
                <Button onClick={handleSave} disabled={saving} data-testid="save-service-btn">
                  {saving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                  {editing ? "Update" : "Create"}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      ) : services.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-muted-foreground mb-4">No services yet</p>
          <Button onClick={openCreateDialog}>
            <Plus className="w-4 h-4 mr-2" />
            Add Your First Service
          </Button>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {services.map((service) => (
            <Card
              key={service.id}
              className={`p-4 relative ${!service.available ? "opacity-60" : ""}`}
              data-testid={`service-card-${service.id}`}
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-semibold text-lg">{service.name}</h3>
                  {!service.available && (
                    <span className="text-xs text-amber-500 font-medium">Unavailable</span>
                  )}
                </div>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => openEditDialog(service)}
                    data-testid={`edit-service-${service.id}`}
                  >
                    <Pencil className="w-4 h-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-destructive hover:text-destructive"
                    onClick={() => handleDelete(service)}
                    data-testid={`delete-service-${service.id}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>

              {service.description && (
                <p className="text-sm text-muted-foreground mb-3 line-clamp-2">
                  {service.description}
                </p>
              )}

              <div className="flex items-center gap-4 text-sm">
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <Clock className="w-4 h-4" />
                  <span>{formatDuration(service.duration_minutes)}</span>
                </div>
                <div className="flex items-center gap-1.5 text-muted-foreground">
                  <DollarSign className="w-4 h-4" />
                  <span>{formatPrice(service.price_cents)}</span>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
