import { useCallback, useEffect, useState } from "react";
import { useAppSession } from "@/context/AppSessionContext";
import { getAdminCostAnalytics } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { DollarSign, Phone, MessageSquare, Zap, TrendingUp, TrendingDown, Loader2, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

const ADMIN_CLERK_ID = import.meta.env.VITE_ADMIN_CLERK_ID || "";

const AdminPage = () => {
  const { activeRestaurant } = useAppSession();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState("30");
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getAdminCostAnalytics(parseInt(days));
      setData(res.data);
      setIsAdmin(true);
    } catch (err: any) {
      if (err?.response?.status === 403) {
        setIsAdmin(false);
      } else {
        toast.error("Failed to load admin analytics");
      }
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) return (
    <div className="flex items-center justify-center py-20">
      <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
    </div>
  );

  if (isAdmin === false) return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      <ShieldAlert className="w-12 h-12 text-destructive/50" />
      <h2 className="font-display font-bold text-xl">Access Denied</h2>
      <p className="text-sm text-muted-foreground">This page is restricted to administrators.</p>
    </div>
  );

  if (!data) return null;

  const { overall, per_restaurant } = data;

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-display font-bold">Admin — Cost Analytics</h1>
          <p className="text-sm text-muted-foreground mt-1">Internal COGS tracking — not visible to business owners</p>
        </div>
        <Select value={days} onValueChange={setDays}>
          <SelectTrigger className="w-32 h-9 rounded-xl">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">Last 7 days</SelectItem>
            <SelectItem value="30">Last 30 days</SelectItem>
            <SelectItem value="90">Last 90 days</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Overall Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card className="premium-card p-4">
          <div className="flex items-center gap-2 mb-2">
            <Phone className="w-4 h-4 text-muted-foreground" />
            <p className="text-xs text-muted-foreground font-medium">Total Calls</p>
          </div>
          <p className="text-2xl font-display font-bold">{overall.total_calls}</p>
        </Card>
        <Card className="premium-card p-4">
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="w-4 h-4 text-destructive" />
            <p className="text-xs text-muted-foreground font-medium">Total COGS</p>
          </div>
          <p className="text-2xl font-display font-bold">${overall.total_cost_dollars.toFixed(2)}</p>
          <p className="text-xs text-muted-foreground">${(overall.avg_cost_per_call_cents / 100).toFixed(3)}/call avg</p>
        </Card>
        <Card className="premium-card p-4">
          <div className="flex items-center gap-2 mb-2">
            <DollarSign className="w-4 h-4 text-emerald-500" />
            <p className="text-xs text-muted-foreground font-medium">AI Revenue</p>
          </div>
          <p className="text-2xl font-display font-bold">${overall.total_revenue_dollars.toFixed(2)}</p>
          <p className="text-xs text-muted-foreground">from orders/bookings</p>
        </Card>
        <Card className="premium-card p-4">
          <div className="flex items-center gap-2 mb-2">
            {overall.gross_margin_pct > 80
              ? <TrendingUp className="w-4 h-4 text-emerald-500" />
              : <TrendingDown className="w-4 h-4 text-destructive" />
            }
            <p className="text-xs text-muted-foreground font-medium">Gross Margin</p>
          </div>
          <p className="text-2xl font-display font-bold">{overall.gross_margin_pct.toFixed(1)}%</p>
          <p className="text-xs text-muted-foreground">{overall.total_sms_sent} SMS sent</p>
        </Card>
      </div>

      {/* Cost Breakdown */}
      <Card className="premium-card p-6">
        <h3 className="font-display font-bold text-lg mb-4">Per Business Breakdown</h3>
        {per_restaurant.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-8">No call data yet for this period.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/50">
                  <th className="text-left py-2 pr-4 font-medium text-muted-foreground">Business</th>
                  <th className="text-right py-2 px-3 font-medium text-muted-foreground">Calls</th>
                  <th className="text-right py-2 px-3 font-medium text-muted-foreground">Voice Cost</th>
                  <th className="text-right py-2 px-3 font-medium text-muted-foreground">SMS Cost</th>
                  <th className="text-right py-2 px-3 font-medium text-muted-foreground">AI Cost</th>
                  <th className="text-right py-2 px-3 font-medium text-muted-foreground">Total COGS</th>
                  <th className="text-right py-2 px-3 font-medium text-muted-foreground">Revenue</th>
                  <th className="text-right py-2 pl-3 font-medium text-muted-foreground">Avg Duration</th>
                </tr>
              </thead>
              <tbody>
                {per_restaurant.map((r: any) => (
                  <tr key={r.restaurant_id} className="border-b border-border/30 hover:bg-muted/20 transition-colors">
                    <td className="py-3 pr-4">
                      <p className="font-medium">{r.restaurant_name}</p>
                      <p className="text-xs text-muted-foreground">{r.sms_count} SMS</p>
                    </td>
                    <td className="text-right py-3 px-3">{r.total_calls}</td>
                    <td className="text-right py-3 px-3 text-muted-foreground">${r.voice_cost_dollars.toFixed(3)}</td>
                    <td className="text-right py-3 px-3 text-muted-foreground">${r.sms_cost_dollars.toFixed(3)}</td>
                    <td className="text-right py-3 px-3 text-muted-foreground">${r.gemini_cost_dollars.toFixed(4)}</td>
                    <td className="text-right py-3 px-3 font-medium text-destructive">${r.cost_dollars.toFixed(3)}</td>
                    <td className="text-right py-3 px-3 font-medium text-emerald-600">${r.revenue_dollars.toFixed(2)}</td>
                    <td className="text-right py-3 pl-3 text-muted-foreground">{r.avg_duration_seconds}s</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-border">
                  <td className="py-3 pr-4 font-bold">Total</td>
                  <td className="text-right py-3 px-3 font-bold">{overall.total_calls}</td>
                  <td className="text-right py-3 px-3"></td>
                  <td className="text-right py-3 px-3"></td>
                  <td className="text-right py-3 px-3"></td>
                  <td className="text-right py-3 px-3 font-bold text-destructive">${overall.total_cost_dollars.toFixed(3)}</td>
                  <td className="text-right py-3 px-3 font-bold text-emerald-600">${overall.total_revenue_dollars.toFixed(2)}</td>
                  <td className="text-right py-3 pl-3"></td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </Card>

      {/* Cost per call benchmark */}
      <Card className="premium-card p-6">
        <h3 className="font-display font-bold text-lg mb-2">Cost Benchmarks</h3>
        <div className="grid sm:grid-cols-3 gap-4 mt-4">
          <div className="p-4 rounded-xl bg-muted/30">
            <p className="text-xs text-muted-foreground mb-1">Telnyx Voice Rate</p>
            <p className="font-display font-bold">$0.0085/min</p>
            <p className="text-xs text-muted-foreground mt-1">inbound US local</p>
          </div>
          <div className="p-4 rounded-xl bg-muted/30">
            <p className="text-xs text-muted-foreground mb-1">Telnyx SMS Rate</p>
            <p className="font-display font-bold">$0.0083/msg</p>
            <p className="text-xs text-muted-foreground mt-1">US outbound</p>
          </div>
          <div className="p-4 rounded-xl bg-muted/30">
            <p className="text-xs text-muted-foreground mb-1">Gemini Live</p>
            <p className="font-display font-bold">$0.00</p>
            <p className="text-xs text-muted-foreground mt-1">free preview</p>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default AdminPage;