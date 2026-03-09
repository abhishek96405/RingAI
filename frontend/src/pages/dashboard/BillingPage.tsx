import { useCallback, useEffect, useState } from "react";
import { useAppSession } from "@/context/AppSessionContext";
import { createBillingCheckout, getRestaurant, getRestaurantId } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { CreditCard } from "lucide-react";
import { toast } from "sonner";

const BillingPage = () => {
  const { activeRestaurant } = useAppSession();
  const [restaurant, setRestaurant] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const fetchRestaurant = useCallback(async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const res = await getRestaurant(restaurantId);
      setRestaurant(res.data);
    } catch {
      toast.error("Failed to load billing info");
    } finally {
      setLoading(false);
    }
  }, [activeRestaurant]);

  useEffect(() => { fetchRestaurant(); }, [fetchRestaurant]);

  const manageBilling = async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const res = await createBillingCheckout({ restaurant_id: restaurantId });
      const url = res?.data?.checkout_url;
      if (!url) return toast.error("Billing checkout URL not available");
      window.location.href = url;
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to open billing");
    }
  };

  if (loading) return <Card className="premium-card h-48 animate-pulse" />;

  return (
    <div className="space-y-8 max-w-4xl">
      <Card className="premium-card p-6">
        <h3 className="font-display font-bold text-lg mb-4 flex items-center gap-2"><CreditCard className="w-4 h-4" /> Billing & Plan</h3>
        <div className="flex items-center gap-4 p-4 rounded-lg bg-primary/5 border border-primary/20 mb-6">
          <div className="flex-1">
            <p className="text-sm font-display font-semibold">{restaurant?.plan || "No plan assigned"}</p>
            <p className="text-xs text-muted-foreground">Billing status will appear here once Stripe is fully connected.</p>
          </div>
          <Badge variant="secondary" className="border-0">{restaurant?.billing_status || "Not configured"}</Badge>
        </div>
        <div className="grid sm:grid-cols-3 gap-4">
          <div className="p-4 rounded-lg bg-muted/30"><p className="text-xs text-muted-foreground">Monthly Calls</p><p className="text-lg font-display font-bold">{restaurant?.monthly_call_count || 0}</p></div>
          <div className="p-4 rounded-lg bg-muted/30"><p className="text-xs text-muted-foreground">Billing Status</p><p className="text-lg font-display font-bold">{restaurant?.billing_status || "--"}</p></div>
          <div className="p-4 rounded-lg bg-muted/30"><p className="text-xs text-muted-foreground">Next Billing</p><p className="text-lg font-display font-bold">--</p></div>
        </div>
        <Separator className="my-6" />
        <Button variant="outline" size="sm" onClick={manageBilling}>Manage Subscription</Button>
      </Card>
    </div>
  );
};

export default BillingPage;
