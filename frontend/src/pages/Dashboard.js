import { useState, useEffect, useCallback } from "react";
import { AppLayout } from "@/layouts/AppLayout";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Phone,
  TrendingUp,
  DollarSign,
  Clock,
  Star,
  ShieldCheck,
  ArrowUpRight,
  PhoneCall,
} from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from "recharts";
import { getAnalyticsSummary, getRestaurantId } from "@/lib/api";
import { toast } from "sonner";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";

const StatCard = ({ icon: Icon, label, value, subtext, trend, iconColor }) => (
  <Card className="p-5 border-border bg-card hover:shadow-md transition-shadow">
    <div className="flex items-start justify-between">
      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${iconColor || 'bg-primary/10 text-primary'}`}>
        <Icon className="w-5 h-5" />
      </div>
      {trend && (
        <Badge variant="secondary" className="text-xs border-0 bg-success/10 text-success">
          <ArrowUpRight className="w-3 h-3 mr-0.5" />
          {trend}
        </Badge>
      )}
    </div>
    <div className="mt-3">
      <p className="text-2xl font-heading font-bold text-foreground">{value}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
    </div>
    {subtext && <p className="text-xs text-muted-foreground mt-2">{subtext}</p>}
  </Card>
);

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-card border border-border rounded-lg p-3 shadow-md">
        <p className="text-sm font-medium text-foreground">{label}</p>
        {payload.map((entry, i) => (
          <p key={i} className="text-xs text-muted-foreground mt-1">
            <span className="font-medium" style={{ color: entry.color }}>{entry.name}:</span>{" "}
            {entry.name === "revenue" ? `$${entry.value.toFixed(0)}` : entry.value}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const res = await getAnalyticsSummary();
      setData(res.data);
    } catch (err) {
      toast.error("Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleSimulateCall = async () => {
    try {
      await simulateCall();
      toast.success("Demo call simulated!");
      fetchData();
    } catch (err) {
      toast.error("Failed to simulate call");
    }
  };

  if (loading) {
    return (
      <AppLayout>
        <div className="p-6 space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <Card key={i} className="p-5 border-border bg-card animate-pulse">
                <div className="w-10 h-10 rounded-lg bg-muted" />
                <div className="mt-3 h-7 w-20 bg-muted rounded" />
                <div className="mt-1 h-4 w-32 bg-muted rounded" />
              </Card>
            ))}
          </div>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="p-4 lg:p-6 space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-heading font-bold text-foreground">Dashboard</h1>
            <p className="text-sm text-muted-foreground">Overview of your AI phone agent performance</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleSimulateCall}>
              <Zap className="w-4 h-4" />
              Simulate Call
            </Button>
            <Button variant="premium" size="sm" asChild>
              <Link to="/calls">View All Calls</Link>
            </Button>
          </div>
        </div>

        {/* KPI Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            icon={Phone}
            label="Total Calls This Week"
            value={data?.calls_this_week || 0}
            trend="+12%"
            iconColor="bg-primary/10 text-primary"
          />
          <StatCard
            icon={DollarSign}
            label="Revenue This Week"
            value={`$${((data?.revenue_this_week || 0) / 100).toFixed(0)}`}
            trend="+8%"
            iconColor="bg-success/10 text-success"
          />
          <StatCard
            icon={Star}
            label="Avg Quality Score"
            value={`${data?.avg_quality_score || 0}/100`}
            subtext="Based on AI analysis"
            iconColor="bg-accent/10 text-accent"
          />
          <StatCard
            icon={ShieldCheck}
            label="AI Containment Rate"
            value={`${data?.ai_containment_rate || 0}%`}
            subtext={`${data?.escalated_calls || 0} escalated`}
            iconColor="bg-primary/10 text-primary"
          />
        </div>

        {/* Charts Row */}
        <div className="grid lg:grid-cols-3 gap-4">
          {/* Call Volume Chart */}
          <Card className="lg:col-span-2 p-5 border-border bg-card">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-heading font-semibold text-foreground">Call Volume & Revenue</h3>
                <p className="text-xs text-muted-foreground">Last 7 days</p>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data?.daily_call_data || []} barGap={4}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="label" tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }} />
                <YAxis yAxisId="left" tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }} />
                <Tooltip content={<CustomTooltip />} />
                <Bar yAxisId="left" dataKey="calls" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} name="calls" />
                <Bar yAxisId="right" dataKey="revenue" fill="hsl(var(--accent))" radius={[4, 4, 0, 0]} name="revenue" />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          {/* Hourly Distribution */}
          <Card className="p-5 border-border bg-card">
            <div className="mb-4">
              <h3 className="text-sm font-heading font-semibold text-foreground">Call Distribution</h3>
              <p className="text-xs text-muted-foreground">By hour of day</p>
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={(data?.hourly_distribution || []).filter(h => h.calls > 0)}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="hour" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} />
                <YAxis tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} />
                <Tooltip content={<CustomTooltip />} />
                <Area type="monotone" dataKey="calls" stroke="hsl(var(--primary))" fill="hsl(var(--primary) / 0.1)" name="calls" />
              </AreaChart>
            </ResponsiveContainer>
          </Card>
        </div>

        {/* Bottom Row */}
        <div className="grid lg:grid-cols-3 gap-4">
          {/* Recent Calls */}
          <Card className="lg:col-span-2 p-5 border-border bg-card">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-heading font-semibold text-foreground">Recent Calls</h3>
              <Button variant="ghost" size="sm" asChild>
                <Link to="/calls">View All</Link>
              </Button>
            </div>
            <div className="space-y-3">
              {(data?.recent_calls || []).map((call, i) => (
                <motion.div
                  key={call.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="flex items-center gap-3 p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
                >
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                    call.status === 'COMPLETED' ? 'bg-success/10 text-success' :
                    call.status === 'ESCALATED' ? 'bg-accent/10 text-accent' :
                    'bg-destructive/10 text-destructive'
                  }`}>
                    <PhoneCall className="w-3.5 h-3.5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {call.caller_name || call.caller_number}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {call.duration_seconds ? `${Math.floor(call.duration_seconds / 60)}m ${call.duration_seconds % 60}s` : '--'}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-medium text-foreground">
                      {call.order_total ? `$${(call.order_total / 100).toFixed(2)}` : '--'}
                    </p>
                    <Badge variant="secondary" className={`text-xs border-0 ${
                      call.status === 'COMPLETED' ? 'bg-success/10 text-success' :
                      call.status === 'ESCALATED' ? 'bg-accent/10 text-accent' :
                      'bg-destructive/10 text-destructive'
                    }`}>
                      {call.status}
                    </Badge>
                  </div>
                </motion.div>
              ))}
              {(!data?.recent_calls || data.recent_calls.length === 0) && (
                <p className="text-sm text-muted-foreground text-center py-8">No calls yet</p>
              )}
            </div>
          </Card>

          {/* Top Items */}
          <Card className="p-5 border-border bg-card">
            <h3 className="text-sm font-heading font-semibold text-foreground mb-4">Top Ordered Items</h3>
            <div className="space-y-3">
              {(data?.top_items || []).slice(0, 8).map((item, i) => (
                <div key={item.name} className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <span className="text-xs font-medium text-muted-foreground w-5">{i + 1}.</span>
                    <span className="text-sm text-foreground truncate">{item.name}</span>
                  </div>
                  <Badge variant="secondary" className="text-xs border-0">
                    {item.count}x
                  </Badge>
                </div>
              ))}
              {(!data?.top_items || data.top_items.length === 0) && (
                <p className="text-sm text-muted-foreground text-center py-4">No order data yet</p>
              )}
            </div>
          </Card>
        </div>
      </div>
    </AppLayout>
  );
}
