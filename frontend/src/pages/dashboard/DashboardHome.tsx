import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, AudioLines, CheckCircle2, Download } from "lucide-react";
import { activateRestaurant, exportAnalytics, getAnalyticsSummary, getRestaurantId } from "@/lib/api";
import { useAppSession } from "@/context/AppSessionContext";
import { toast } from "sonner";
import type { DashboardStats } from "@/types";

function formatHour(h: unknown): string | null {
  if (h === null || h === undefined || h === "") return null;
  const n = Number(h);
  if (Number.isNaN(n)) return String(h);
  const hr = ((n + 11) % 12) + 1;
  return `${hr} ${n < 12 ? "AM" : "PM"}`;
}

function buildBriefing(calls: number, escalated: number, busiest: string | null, periodWord: string) {
  if (!calls) {
    return `No calls yet this ${periodWord}. Your briefing fills in as Duuutah starts answering.`;
  }
  let s = `Duuutah answered ${calls} call${calls === 1 ? "" : "s"} this ${periodWord}`;
  if (busiest) s += `, busiest around ${busiest}`;
  s += ". ";
  s += escalated > 0
    ? `${escalated} ${escalated === 1 ? "call needed" : "calls needed"} a human hand-off.`
    : "Every one was handled without a hand-off.";
  return s;
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: Array<{ color?: string; name?: string; value?: number | string }>;
  label?: string | number;
}

function CustomTooltip({ active, payload, label }: ChartTooltipProps) {
  if (active && payload && payload.length) {
    return (
      <div className="rounded-xl border border-line bg-[#FFFDF9] p-3 shadow-lg">
        <p className="text-sm font-semibold">{label}</p>
        {payload.map((entry, i) => (
          <p key={i} className="text-xs text-ink-soft mt-1">
            <span className="font-medium" style={{ color: entry.color }}>{entry.name}:</span>{" "}
            {entry.name === "revenue" ? `$${Number(entry.value).toFixed(0)}` : entry.value}
          </p>
        ))}
      </div>
    );
  }
  return null;
}

const WAVE_DELAYS = [0, 0.1, 0.2, 0.3, 0.15, 0.25, 0.35, 0.05, 0.2, 0.3, 0.12, 0.28];

const DashboardHome = () => {
  const { activeRestaurant } = useAppSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<"weekly" | "monthly">("weekly");
  const [exporting, setExporting] = useState(false);
  const [exportStart, setExportStart] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 10);
  });
  const [exportEnd, setExportEnd] = useState(() => new Date().toISOString().slice(0, 10));

  useEffect(() => {
    if (searchParams.get("billing") !== "success") return;
    const restaurantId = activeRestaurant?.id || getRestaurantId();
    if (!restaurantId) return;
    activateRestaurant(restaurantId)
      .then(() => toast.success("Your AI phone agent is live!"))
      .catch(() => {});
    setSearchParams({}, { replace: true });
  }, [searchParams, activeRestaurant, setSearchParams]);

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
      if (!restaurantId) { setData(null); return; }
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
    const handleVisibility = () => { if (document.visibilityState === "visible") fetchData(); };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [fetchData]);

  if (loading) {
    return (
      <div className="dash space-y-6">
        <div className="dash-hero rounded-[2rem] h-48 animate-pulse" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {[...Array(4)].map((_, i) => <div key={i} className="dash-card h-32 animate-pulse" />)}
        </div>
      </div>
    );
  }

  const d: DashboardStats = data || {};
  const periodWord = period === "weekly" ? "week" : "month";
  const calls = Number(period === "weekly" ? d.calls_this_week : d.calls_this_month) || 0;
  const revenue = Math.round((Number(period === "weekly" ? d.revenue_this_week : d.revenue_this_month) || 0) / 100);
  const quality = Number(d.avg_quality_score) || 0;
  const containment = Number(d.ai_containment_rate) || 0;
  const escalated = Number(d.escalated_calls) || 0;
  const chartData = (period === "weekly" ? d.daily_call_data : d.monthly_call_data) || [];
  const topItems = d.top_items || [];
  const maxCount = topItems.length ? Math.max(...topItems.map((t) => Number(t.count) || 0), 1) : 1;

  const hourly = (d.hourly_distribution || []).filter((h) => (Number(h.calls) || 0) > 0);
  const busiest = hourly.length
    ? formatHour(hourly.reduce((a, b) => ((Number(b.calls) || 0) > (Number(a.calls) || 0) ? b : a)).hour)
    : null;

  const briefing = buildBriefing(calls, escalated, busiest, periodWord);
  const dateLabel = new Date().toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });

  return (
    <div className="dash space-y-8">
      {/* AI BRIEFING HERO */}
      <section className="dash-hero rounded-[2rem] p-7 lg:p-9 relative overflow-hidden">
        <AudioLines className="absolute -right-8 -bottom-12 w-72 h-72 text-coral/[0.07]" strokeWidth={1.5} />
        <div className="relative">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <p className="eyebrow">Your daily briefing · {dateLabel}</p>
          </div>
          <p className="font-display font-semibold mt-5 max-w-2xl leading-snug tracking-tight text-xl lg:text-2xl">{briefing}</p>

          <div className="mt-8 flex flex-wrap items-end gap-x-12 gap-y-6">
            <div className="flex items-end gap-4">
              <span className="relative font-display font-extrabold leading-[0.9]" style={{ fontSize: "clamp(3rem,6.5vw,4.75rem)" }}>
                {calls}
                <svg className="absolute left-0 -bottom-2 w-full" style={{ height: 12, overflow: "visible" }} viewBox="0 0 200 12" preserveAspectRatio="none" fill="none">
                  <path d="M3,8 C56,2 150,2 197,7" stroke="#E8502E" strokeWidth={3.5} strokeLinecap="round" fill="none" vectorEffect="non-scaling-stroke" />
                </svg>
              </span>
              <div className="mb-1.5">
                <p className="text-sm font-semibold leading-tight">calls answered</p>
                <span className="chip b-coral mt-1 inline-block">{containment}% handled by AI</span>
              </div>
            </div>

            <div className="flex gap-9">
              <div><p className="font-display font-extrabold text-2xl">${revenue.toLocaleString()}</p><p className="text-xs text-ink-soft mt-0.5">Revenue</p></div>
              <div><p className="font-display font-extrabold text-2xl">{quality}<span className="text-base text-ink-soft">/100</span></p><p className="text-xs text-ink-soft mt-0.5">Quality</p></div>
              <div><p className="font-display font-extrabold text-2xl">{escalated}</p><p className="text-xs text-ink-soft mt-0.5">Escalated</p></div>
            </div>

            <div className="flex items-center gap-3 ml-auto">
              <div className="wf w-24">
                {WAVE_DELAYS.map((delay, i) => <span key={i} style={{ animationDelay: `-${delay}s` }} />)}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* NEEDS YOU */}
      <section>
        <p className="eyebrow mb-4">Needs you</p>
        {escalated > 0 ? (
          <div className="dash-card card-hover p-5 flex items-start gap-3.5" style={{ borderLeft: "4px solid #F2A93B" }}>
            <span className="h-9 w-9 rounded-xl flex items-center justify-center b-honey shrink-0"><AlertTriangle className="w-4 h-4" /></span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold">{escalated} call{escalated === 1 ? "" : "s"} needed a human this {periodWord}</p>
              <p className="text-xs text-ink-soft mt-0.5">Review the transcripts to see what those callers needed.</p>
            </div>
            <Link to="/dashboard/calls?status=ESCALATED" className="text-xs font-semibold text-coral hover:text-coral-deep shrink-0">Review →</Link>
          </div>
        ) : (
          <div className="dash-card p-5 flex items-center gap-3.5">
            <span className="h-9 w-9 rounded-xl flex items-center justify-center b-success shrink-0"><CheckCircle2 className="w-4 h-4" /></span>
            <div>
              <p className="text-sm font-semibold">All clear</p>
              <p className="text-xs text-ink-soft mt-0.5">Nothing needs your attention right now.</p>
            </div>
          </div>
        )}
      </section>

      {/* CHART + TOP ITEMS */}
      <section className="grid lg:grid-cols-3 gap-6">
        <div className="dash-card card-hover p-6 lg:col-span-2">
          <div className="flex items-center justify-between mb-6 gap-4 flex-wrap">
            <div><p className="eyebrow mb-2">Calls & revenue</p><h3 className="font-display font-bold text-lg">Last {period === "weekly" ? "7 days" : "30 days"}</h3></div>
            <div className="flex items-center gap-2 flex-wrap">
              <div className="flex rounded-xl border border-line overflow-hidden bg-[#FFFDF9]">
                <button onClick={() => setPeriod("weekly")} className={period === "weekly" ? "px-3 py-1.5 text-sm font-semibold bg-coral text-white" : "px-3 py-1.5 text-sm font-medium text-ink-soft hover:bg-line/40"}>Weekly</button>
                <button onClick={() => setPeriod("monthly")} className={period === "monthly" ? "px-3 py-1.5 text-sm font-semibold bg-coral text-white" : "px-3 py-1.5 text-sm font-medium text-ink-soft hover:bg-line/40"}>Monthly</button>
              </div>
              <input type="date" value={exportStart} onChange={(e) => setExportStart(e.target.value)} className="text-sm border border-line rounded-xl px-2 py-1.5 bg-[#FFFDF9]" />
              <span className="text-sm text-ink-soft">to</span>
              <input type="date" value={exportEnd} onChange={(e) => setExportEnd(e.target.value)} className="text-sm border border-line rounded-xl px-2 py-1.5 bg-[#FFFDF9]" />
              <button onClick={handleExport} disabled={exporting} className="inline-flex items-center gap-1.5 border border-line bg-[#FFFDF9] hover:border-ink/25 px-3 py-1.5 rounded-xl text-sm font-semibold transition disabled:opacity-50"><Download className="w-3.5 h-3.5" />Export</button>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-ink-soft mb-4">
            <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-coral" />Calls</span>
            <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-success" />Revenue</span>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={chartData} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="#EBE2D8" />
              <XAxis dataKey="label" tick={{ fontSize: 12, fill: "#6F6259" }} stroke="#EBE2D8" />
              <YAxis yAxisId="left" tick={{ fontSize: 12, fill: "#6F6259" }} stroke="#EBE2D8" />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 12, fill: "#6F6259" }} stroke="#EBE2D8" />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(232,80,46,0.06)" }} />
              <Bar yAxisId="left" dataKey="calls" fill="#E8502E" radius={[6, 6, 0, 0]} name="calls" />
              <Bar yAxisId="right" dataKey="revenue" fill="#3E9E78" radius={[6, 6, 0, 0]} name="revenue" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="dash-card card-hover p-6">
          <p className="eyebrow mb-2">What they're ordering</p>
          <h3 className="font-display font-bold text-lg mb-5">Top items</h3>
          <div className="space-y-4">
            {topItems.length ? topItems.slice(0, 6).map((it) => (
              <div key={it.name}>
                <div className="flex justify-between text-sm mb-1.5"><span className="font-medium truncate pr-2">{it.name}</span><span className="text-ink-soft">{it.count}</span></div>
                <div className="track"><div className="fill" style={{ width: `${Math.round(((Number(it.count) || 0) / maxCount) * 100)}%` }} /></div>
              </div>
            )) : <p className="text-sm text-ink-soft text-center py-6">No order data yet</p>}
          </div>
        </div>
      </section>
    </div>
  );
};

export default DashboardHome;
