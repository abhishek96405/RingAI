import { useCallback, useEffect, useState } from "react";
import { useAppSession } from "@/context/AppSessionContext";
import { createBillingCheckout, createBillingPortal, getInvoices, getRestaurant, getRestaurantId } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import { 
  CreditCard, 
  Check, 
  Zap, 
  Phone, 
  Bot, 
  TrendingUp,
  ExternalLink,
  AlertCircle,
  Loader2
} from "lucide-react";
import { toast } from "sonner";

const plans = [
  {
    name: "Starter",
    price: 199,
    calls: 500,
    features: [
      "500 AI calls/month ($0.25/call overage)",
      "AI pickup order taking",
      "1 AI voice (default)",
      "1 language",
      "Full menu & modifier management",
      "POS integration (Clover, Square, Toast)",
      "SMS order confirmations",
      "Full analytics dashboard",
      "Call history & transcripts",
      "Email support",
    ],
    popular: false,
  },
  {
    name: "Pro",
    price: 349,
    calls: 1000,
    features: [
      "Everything in Starter, plus:",
      "1,000 AI calls/month ($0.20/call overage)",
      "AI delivery order handling",
      "AI table reservations",
      "AI upselling during calls",
      "Customer recognition",
      "Auto AI learning",
      "8 premium voice options",
      "Multi-language support",
      "Customer CRM profiles",
      "Priority support",
    ],
    popular: true,
  },
];

const BillingPage = () => {
  const { activeRestaurant } = useAppSession();
  const [restaurant, setRestaurant] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [upgrading, setUpgrading] = useState<string | null>(null);
  const [invoices, setInvoices] = useState<any[]>([]);

  const fetchRestaurant = useCallback(async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const [resR, resI] = await Promise.all([
        getRestaurant(restaurantId),
        getInvoices(restaurantId).catch(() => ({ data: { invoices: [] } })),
      ]);
      setRestaurant(resR.data);
      setInvoices(resI.data.invoices || []);
    } catch {
      toast.error("Failed to load billing info");
    } finally {
      setLoading(false);
    }
  }, [activeRestaurant]);

  useEffect(() => { fetchRestaurant(); }, [fetchRestaurant]);

  const handleUpgrade = async (planName: string) => {
    setUpgrading(planName);
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const res = await createBillingCheckout({ 
        restaurant_id: restaurantId,
        plan: planName.toLowerCase(),
      });
      const url = res?.data?.checkout_url;
      if (!url) {
        toast.error("Billing checkout URL not available. Please configure Stripe.");
        return;
      }
      window.location.href = url;
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to start checkout");
    } finally {
      setUpgrading(null);
    }
  };

  const manageBilling = async () => {
    try {
      const restaurantId = activeRestaurant?.id || getRestaurantId();
      const res = await createBillingPortal({ restaurant_id: restaurantId });
      const url = res?.data?.portal_url;
      if (!url) return toast.error("Billing portal not available");
      window.location.href = url;
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || "Failed to open billing portal");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const currentPlan = restaurant?.plan || "Free";
  const billingStatus = restaurant?.billing_status || "inactive";
  const trialEndsAt = restaurant?.trial_ends_at ? new Date(restaurant.trial_ends_at) : null;
  const trialDaysLeft = trialEndsAt ? Math.max(0, Math.ceil((trialEndsAt.getTime() - Date.now()) / (1000 * 60 * 60 * 24))) : 0;
  const callCount = restaurant?.monthly_call_count || 0;
  const callLimit = restaurant?.monthly_call_limit || 500;
  const usagePercent = callLimit > 0 ? Math.min(100, (callCount / callLimit) * 100) : 0;

  return (
    <div className="space-y-8 max-w-6xl" data-testid="billing-page">
      {/* Current Plan Overview */}
      <Card className="premium-card p-6">
        <div className="flex items-start justify-between mb-6">
          <div>
            <h3 className="font-display font-bold text-lg flex items-center gap-2">
              <CreditCard className="w-5 h-5" /> 
              Current Plan
            </h3>
            <p className="text-sm text-muted-foreground mt-1">
              Manage your subscription and billing
            </p>
          </div>
          <Badge
            variant={billingStatus === "active" || billingStatus === "trialing" ? "default" : "secondary"}
            className={billingStatus === "active" ? "bg-success text-white" : billingStatus === "trialing" ? "bg-primary text-white" : ""}
          >
            {billingStatus === "active" ? "Active" : billingStatus === "trialing" ? "Trial" : billingStatus === "past_due" ? "Past Due" : "Inactive"}
          </Badge>
        </div>

        <div className="grid sm:grid-cols-4 gap-4 mb-6">
          <div className="p-4 rounded-xl bg-gradient-to-br from-primary/10 to-primary/5 border border-primary/20">
            <div className="flex items-center gap-2 mb-2">
              <Zap className="w-4 h-4 text-primary" />
              <p className="text-xs text-muted-foreground font-medium">Current Plan</p>
            </div>
            <p className="text-xl font-display font-bold">{currentPlan}</p>
          </div>
          <div className="p-4 rounded-xl bg-muted/30">
            <div className="flex items-center gap-2 mb-2">
              <Phone className="w-4 h-4 text-muted-foreground" />
              <p className="text-xs text-muted-foreground font-medium">Calls This Month</p>
            </div>
            <p className="text-xl font-display font-bold">{callCount} <span className="text-sm text-muted-foreground font-normal">/ {callLimit}</span></p>
            <Progress value={usagePercent} className={`h-1.5 mt-2 ${usagePercent > 80 ? "[&>div]:bg-destructive" : usagePercent > 60 ? "[&>div]:bg-warning" : ""}`} />
            {billingStatus === "trialing" && <p className="text-[10px] text-muted-foreground mt-1">No overage during trial</p>}
          </div>
          <div className="p-4 rounded-xl bg-muted/30">
            <div className="flex items-center gap-2 mb-2">
              <Bot className="w-4 h-4 text-muted-foreground" />
              <p className="text-xs text-muted-foreground font-medium">AI Containment</p>
            </div>
            <p className="text-xl font-display font-bold">{restaurant?.ai_containment_rate || 0}%</p>
          </div>
          <div className="p-4 rounded-xl bg-muted/30">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp className="w-4 h-4 text-muted-foreground" />
              <p className="text-xs text-muted-foreground font-medium">Revenue via AI</p>
            </div>
            <p className="text-xl font-display font-bold">${((restaurant?.total_revenue || 0) / 100).toFixed(0)}</p>
          </div>
        </div>

        {billingStatus !== "active" && billingStatus !== "trialing" && (
          <div className="flex items-center gap-3 p-4 rounded-xl bg-warning/10 border border-warning/20 mb-6">
            <AlertCircle className="w-5 h-5 text-warning flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium">No active subscription</p>
              <p className="text-xs text-muted-foreground">Choose a plan below to start using Duuutah AI</p>
            </div>
          </div>
        )}

        <Button 
          variant="outline" 
          size="sm" 
          onClick={manageBilling}
          className="gap-2"
          data-testid="manage-subscription-btn"
        >
          <ExternalLink className="w-4 h-4" />
          Manage Subscription
        </Button>
      </Card>

      {/* Pricing Plans */}
      <div>
        <h3 className="font-display font-bold text-lg mb-4">Available Plans</h3>
        <div className="grid md:grid-cols-2 gap-6 max-w-3xl">
          {plans.map((plan) => (
            <Card 
              key={plan.name}
              className={`p-6 relative ${plan.popular ? "border-primary shadow-lg ring-2 ring-primary/20" : ""}`}
              data-testid={`plan-card-${plan.name.toLowerCase()}`}
            >
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <Badge className="bg-primary text-white">Most Popular</Badge>
                </div>
              )}
              
              <div className="text-center mb-6">
                <h4 className="font-display font-bold text-xl mb-2">{plan.name}</h4>
                <div className="flex items-baseline justify-center gap-1">
                  <span className="text-4xl font-display font-bold">${plan.price}</span>
                  <span className="text-muted-foreground">/month</span>
                </div>
                <p className="text-sm text-muted-foreground mt-2">{plan.calls} calls included</p>
              </div>

              <Separator className="my-6" />

              <ul className="space-y-3 mb-6">
                {plan.features.map((feature, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <Check className="w-4 h-4 text-success mt-0.5 flex-shrink-0" />
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>

              <Button 
                className={`w-full ${plan.popular ? "bg-gradient-primary shadow-glow" : ""}`}
                variant={plan.popular ? "default" : "outline"}
                onClick={() => handleUpgrade(plan.name)}
                disabled={upgrading === plan.name || currentPlan.toLowerCase() === plan.name.toLowerCase()}
                data-testid={`upgrade-${plan.name.toLowerCase()}-btn`}
              >
                {upgrading === plan.name ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Processing...
                  </>
                ) : currentPlan.toLowerCase() === plan.name.toLowerCase() ? (
                  "Current Plan"
                ) : (
                  "Get Started"
                )}
              </Button>
            </Card>
          ))}
        </div>
      </div>

      {/* Trial Status */}
      {billingStatus === "trialing" && trialEndsAt && (
        <Card className="premium-card p-6 border-primary/20 bg-primary/5">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-display font-bold text-lg flex items-center gap-2">
                <Zap className="w-5 h-5 text-primary" />
                Free Trial Active
              </h3>
              <p className="text-sm text-muted-foreground mt-1">
                {trialDaysLeft} day{trialDaysLeft !== 1 ? "s" : ""} remaining — your card will be charged on {trialEndsAt.toLocaleDateString()}
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={manageBilling} className="gap-2">
              Cancel Trial
            </Button>
          </div>
        </Card>
      )}

      {/* Invoice History */}
      {invoices.length > 0 && (
        <Card className="premium-card p-6">
          <h3 className="font-display font-bold text-lg mb-4">Invoice History</h3>
          <div className="space-y-3">
            {invoices.map((inv: any) => (
              <div key={inv.id} className="flex items-center justify-between py-2 border-b border-border/50 last:border-0">
                <div>
                  <p className="text-sm font-medium">{new Date(inv.date * 1000).toLocaleDateString()}</p>
                  <p className="text-xs text-muted-foreground">{inv.description || "Subscription"}</p>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant="secondary" className={`border-0 text-xs ${inv.status === "paid" ? "bg-success/10 text-success" : inv.status === "open" ? "bg-warning/10 text-warning" : "bg-destructive/10 text-destructive"}`}>
                    {inv.status === "paid" ? "Paid" : inv.status === "open" ? "Open" : "Failed"}
                  </Badge>
                  <span className="text-sm font-medium">${(inv.amount / 100).toFixed(2)}</span>
                  {inv.pdf && (
                    <a href={inv.pdf} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline">PDF</a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* FAQ */}
      <Card className="premium-card p-6">
        <h3 className="font-display font-bold text-lg mb-4">Billing FAQ</h3>
        <div className="space-y-4">
          <div>
            <p className="font-medium text-sm">What happens if I exceed my call limit?</p>
            <p className="text-sm text-muted-foreground mt-1">
              You'll be notified when approaching your limit. Overage calls are billed at $0.25/call (Starter) or $0.20/call (Pro).
            </p>
          </div>
          <Separator />
          <div>
            <p className="font-medium text-sm">Can I change plans anytime?</p>
            <p className="text-sm text-muted-foreground mt-1">
              Yes! Upgrades take effect immediately. Downgrades apply at the next billing cycle.
            </p>
          </div>
          <Separator />
          <div>
            <p className="font-medium text-sm">Do you offer refunds?</p>
            <p className="text-sm text-muted-foreground mt-1">
              Cancel within 7 days for free. After 7 days, we charge the current month's fee.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default BillingPage;
