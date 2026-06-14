import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { activateRestaurant, getAnalyticsSummary, getRestaurantId } from "@/lib/api";
import { useAppSession } from "@/context/AppSessionContext";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowUpRight, DollarSign, Phone, PhoneCall, ShieldCheck, Star } from "lucide-react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { exportAnalytics } from "@/lib/api";
import { Download } from "lucide-react";

function StatCard({ icon: Icon, label, value, subtext, iconColor }: any) {
  return (
    <Card className="kpi-card">
      <div className="flex items-start justify-between">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${iconColor || "bg-primary/10 text-primary"}`}>
          <Icon className="w-5 h-5" />
        </div>
        <Badge variant="secondary" className="text-xs border-0 bg-success/10 text-success">
          <ArrowUpRight className="w-3 h-3 mr-0.5" /> Live
        </Badge>
      </div>
      <div className="mt-3">
        <p className="text-2xl font-display font-bold">{value}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
      </div>
      {subtext && <p className="text-xs text-muted-foreground mt-2">{subtext}</p>}
    </Card>
  );
}

function CustomTooltip({ active, payload, label }: any) {
  if (active && payload && payload.length) {
    return (
      <div className="bg-card border border-border rounded-lg p-3 shadow-md">
        <p className="text-sm font-medium">{label}</p>
        {payload.map((entry: any, i: number) => (
          <p key={i} className="text-xs text-muted-foreground mt-1">
            <span className="font-medium" style={{ color: entry.color }}>{entry.name}:</span>{" "}
            {entry.name === "revenue" ? `$${Number(entry.value).toFixed(0)}` : entry.value}
          </p>
        ))}
      </div>
    );
  }
  return null;
}

const DashboardHome = () => {
  const { activeRestaurant } = useAppSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    if (searchParams.get("billing") !== "success") return;
    const restaurantId = activeRestaurant?.id || getRestaurantId();
    if (!restaurantId) return;
    activateRestaurant(restaurantId)
      .then(() => toast.success("Your AI phone agent is live!"))
      .catch(() => {});
    setSearchParams({}, { replace: true });
  }, [searchParams, activeRestaurant]);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<"weekly" | "monthly">("weekly");
  const [exporting, setExporting] = useState(false);
  const [exportStart, setExportStart] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 10);
  });
  const [exportEnd, setExportEnd] = useState(() => new Date().toISOString().slice(0, 10));

  const handleExport = async () => {
    try {
      setExporting(true);
      const res = await exportAnalytics(exportStart, exportEnd);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `duuutah_export_${exportStart}_to_${exportEnd}.csv`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      toast.error("Export failed");
    } finally {
      setExporting(false);
    }
  };

  const fetchData = useCallback(async () => {
    try {
      const restaurantId = getRestaurantId();
      if (!restaurantId) {
        setData(null);
        return;
      }
      const res = await getAnalyticsSummary(restaurantId);
      setData(res.data);
    } catch (err) {
      console.error("Dashboard fetch error", err);
      toast.error("Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  }, []);

  
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30_000);
    const handleVisibility = () => {
      if (document.visibilityState === "visible") fetchData();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [fetchData]);
  

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <div key={i} className="premium-card h-32 animate-pulse" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-display font-bold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Overview of your AI phone agent performance</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex rounded-xl border border-border overflow-hidden">
            <button onClick={() => setPeriod("weekly")} className={`px-3 py-1.5 text-sm ${period === "weekly" ? "bg-primary text-primary-foreground" : "bg-card text-muted-foreground"}`}>Weekly</button>
            <button onClick={() => setPeriod("monthly")} className={`px-3 py-1.5 text-sm ${period === "monthly" ? "bg-primary text-primary-foreground" : "bg-card text-muted-foreground"}`}>Monthly</button>
          </div>
          <div className="flex items-center gap-2">
            <input type="date" value={exportStart} onChange={e => setExportStart(e.target.value)} className="text-sm border border-border rounded-xl px-2 py-1.5 bg-card text-foreground" />
            <span className="text-sm text-muted-foreground">to</span>
            <input type="date" value={exportEnd} onChange={e => setExportEnd(e.target.value)} className="text-sm border border-border rounded-xl px-2 py-1.5 bg-card text-foreground" />
            <Button variant="outline" size="sm" className="rounded-xl" disabled={exporting} onClick={handleExport}>
              <Download className="w-3.5 h-3.5 mr-1" />Export
            </Button>
          </div>
        </div>
      </div>

      {data && data.total_calls === 0 && (
        <Card className="premium-card p-5">
          <h3 className="text-sm font-semibold">No real call data yet</h3>
          <p className="text-sm text-muted-foreground mt-1">Your dashboard will populate after real calls are received by your AI phone agent.</p>
        </Card>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Phone} label={`Total Calls This ${period === "weekly" ? "Week" : "Month"}`} value={period === "weekly" ? data?.calls_this_week || 0 : data?.calls_this_month || 0} iconColor="bg-primary/10 text-primary" />
        <StatCard icon={DollarSign} label={`Revenue This ${period === "weekly" ? "Week" : "Month"}`} value={`$${((period === "weekly" ? data?.revenue_this_week || 0 : data?.revenue_this_month || 0) / 100).toFixed(0)}`} iconColor="bg-success/10 text-success" />
        <StatCard icon={Star} label="Avg Quality Score" value={`${data?.avg_quality_score || 0}/100`} subtext="Based on AI analysis" iconColor="bg-warning/10 text-warning" />
        <StatCard icon={ShieldCheck} label="AI Containment Rate" value={`${data?.ai_containment_rate || 0}%`} subtext={`${data?.escalated_calls || 0} escalated`} iconColor="bg-primary/10 text-primary" />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 premium-card p-6">
          <div className="mb-6">
            <h3 className="font-display font-bold text-lg">Call Volume & Revenue</h3>
            <p className="text-sm text-muted-foreground">Last {period === "weekly" ? "7" : "30"} days</p>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={period === "weekly" ? data?.daily_call_data || [] : data?.monthly_call_data || []} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="label" tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" />
              <YAxis yAxisId="left" tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" />
              <Tooltip content={<CustomTooltip />} />
              <Bar yAxisId="left" dataKey="calls" fill="hsl(var(--primary))" radius={[6, 6, 0, 0]} name="calls" />
              <Bar yAxisId="right" dataKey="revenue" fill="hsl(var(--success))" radius={[6, 6, 0, 0]} name="revenue" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="premium-card p-6">
          <div className="mb-6">
            <h3 className="font-display font-bold text-lg">Call Distribution</h3>
            <p className="text-sm text-muted-foreground">By hour of day</p>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={(data?.hourly_distribution || []).filter((h: any) => h.calls > 0)}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="hour" tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
              <YAxis tick={{ fontSize: 10 }} stroke="hsl(var(--muted-foreground))" />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="calls" stroke="hsl(var(--primary))" fill="hsl(var(--primary) / 0.15)" name="calls" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 premium-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display font-bold text-lg">Recent Calls</h3>
            <Button variant="ghost" size="sm" asChild><Link to="/dashboard/calls">View All</Link></Button>
          </div>
          <div className="space-y-3">
            {(data?.recent_calls || []).map((call: any, i: number) => (
              <motion.div key={call.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="flex items-center gap-3 p-3 rounded-xl bg-muted/30 hover:bg-muted/50 transition-colors">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${call.status === "COMPLETED" ? "bg-success/10 text-success" : call.status === "ESCALATED" ? "bg-warning/10 text-warning" : "bg-destructive/10 text-destructive"}`}>
                  <PhoneCall className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{call.caller_name || call.caller_number}</p>
                  <p className="text-xs text-muted-foreground">{call.duration_seconds ? `${Math.floor(call.duration_seconds / 60)}m ${call.duration_seconds % 60}s` : "--"}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium">{call.order_total ? `$${(call.order_total / 100).toFixed(2)}` : "--"}</p>
                  <Badge variant="secondary" className={`text-xs border-0 ${call.status === "COMPLETED" ? "bg-success/10 text-success" : call.status === "ESCALATED" ? "bg-warning/10 text-warning" : "bg-destructive/10 text-destructive"}`}>{call.status}</Badge>
                </div>
              </motion.div>
            ))}
            {(!data?.recent_calls || data.recent_calls.length === 0) && <p className="text-sm text-muted-foreground text-center py-8">No calls yet</p>}
          </div>
        </div>

        <div className="premium-card p-6">
          <h3 className="font-display font-bold text-lg mb-4">Top Ordered Items</h3>
          <div className="space-y-3">
            {(data?.top_items || []).slice(0, 8).map((item: any, i: number) => (
              <div key={item.name} className="flex items-center justify-between">
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className="text-xs font-medium text-muted-foreground w-5">{i + 1}.</span>
                  <span className="text-sm truncate">{item.name}</span>
                </div>
                <Badge variant="secondary" className="text-xs border-0">{item.count}x</Badge>
              </div>
            ))}
            {(!data?.top_items || data.top_items.length === 0) && <p className="text-sm text-muted-foreground text-center py-4">No order data yet</p>}
          </div>
        </div>
      </div>

    </div>
  );
};

export default DashboardHome;
