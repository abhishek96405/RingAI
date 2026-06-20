import { useCallback, useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { getCall, getCalls } from "@/lib/api";
import { AlertTriangle, Bot, Calendar, CheckCircle2, ChevronLeft, ChevronRight, Clock, Download, Phone, Search, Sparkles, Star, User, XCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { motion } from "framer-motion";
import { toast } from "sonner";
import type { Call, OrderItem, TranscriptEntry } from "@/types";

const statusIcons: Record<string, LucideIcon> = {
  COMPLETED: CheckCircle2,
  ESCALATED: AlertTriangle,
  FAILED: XCircle,
  IN_PROGRESS: Phone,
};

// Warm functional-color tint per status: green = healthy, honey = needs attention,
// red = broken, coral = in progress. Used for both the row icon and the status chip.
const statusTint: Record<string, string> = {
  COMPLETED: "b-success",
  ESCALATED: "b-honey",
  FAILED: "bg-red-500/10 text-red-600",
  IN_PROGRESS: "b-coral",
};

// Pretty label for an order's fulfillment type. "+reservation" marks a dual-intent
// call (food order placed alongside a table reservation). Unknown/missing → Pickup.
const orderTypeLabel = (t?: string): string => {
  switch (t) {
    case "delivery":
      return "Delivery";
    case "reservation":
      return "Reservation";
    case "pickup+reservation":
      return "Pickup + Reservation";
    case "delivery+reservation":
      return "Delivery + Reservation";
    default:
      return "Pickup";
  }
};

const CallsPage = () => {
  const [calls, setCalls] = useState<Call[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [selectedCall, setSelectedCall] = useState<Call | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Date filter state
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [exporting, setExporting] = useState(false);

  const fetchCalls = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = {
        page,
        limit: 15,
        status: statusFilter !== "ALL" ? statusFilter : undefined,
        search: search || undefined,
      };

      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;

      const res = await getCalls(null, params);
      setCalls(res.data.calls || []);
      setTotal(res.data.total || 0);
      setPages(res.data.pages || 1);
    } catch (err) {
      console.error(err);
      toast.error("Failed to load calls");
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter, search, dateFrom, dateTo]);

  useEffect(() => {
    fetchCalls();
  }, [fetchCalls]);

  const openCallDetail = async (callId: string) => {
    try {
      const res = await getCall(callId);
      setSelectedCall(res.data);
      setDrawerOpen(true);
    } catch (err) {
      toast.error("Failed to load call details");
    }
  };

  const formatTime = (isoStr?: string) => {
    if (!isoStr) return "--";
    try {
      return new Date(isoStr).toLocaleString("en-US", {
        month: "short", day: "numeric", hour: "numeric", minute: "2-digit", hour12: true,
      });
    } catch {
      return "--";
    }
  };

  const formatDuration = (seconds?: number) => {
    if (!seconds) return "--";
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  };

  // CSV Export functionality
  const exportToCSV = async () => {
    setExporting(true);
    try {
      const params: Record<string, unknown> = {
        page: 1,
        limit: 1000,
        status: statusFilter !== "ALL" ? statusFilter : undefined,
        search: search || undefined,
      };
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;

      const res = await getCalls(null, params);
      const allCalls = res.data.calls || [];

      if (allCalls.length === 0) {
        toast.error("No calls to export");
        return;
      }

      const headers = [
        "Call ID",
        "Date/Time",
        "Caller Name",
        "Caller Phone",
        "Status",
        "Duration (seconds)",
        "Quality Score",
        "Order Total",
        "Contained by AI",
        "Escalated",
      ];

      const rows = allCalls.map((call: Call) => [
        call.id || "",
        call.started_at || "",
        call.caller_name || "Unknown",
        call.caller_number || "",
        call.status || "",
        call.duration_seconds || 0,
        call.quality_score || "",
        call.order_total ? (call.order_total / 100).toFixed(2) : "0",
        call.contained_by_ai ? "Yes" : "No",
        call.escalated_to_human ? "Yes" : "No",
      ]);

      const csvContent = [
        headers.join(","),
        ...rows.map(row => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")),
      ].join("\n");

      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.setAttribute("href", url);
      link.setAttribute("download", `call_history_${new Date().toISOString().split("T")[0]}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      toast.success(`Exported ${allCalls.length} calls to CSV`);
    } catch (err) {
      console.error(err);
      toast.error("Failed to export calls");
    } finally {
      setExporting(false);
    }
  };

  const clearDateFilters = () => {
    setDateFrom("");
    setDateTo("");
    setPage(1);
  };

  return (
    <div className="dash space-y-6" data-testid="calls-page">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <p className="eyebrow mb-2">Call log</p>
          <h1 className="text-2xl font-display font-bold">Call History</h1>
          <p className="text-sm text-ink-soft mt-1">{total} total calls</p>
        </div>
        <button
          onClick={exportToCSV}
          disabled={exporting || total === 0}
          data-testid="export-csv-btn"
          className="inline-flex items-center gap-2 border border-line bg-[#FFFDF9] hover:border-ink/25 px-4 py-2 rounded-xl text-sm font-semibold transition disabled:opacity-50"
        >
          <Download className="w-4 h-4" />
          {exporting ? "Exporting..." : "Export CSV"}
        </button>
      </div>

      {/* Filters Row */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-soft" />
            <Input
              placeholder="Search by name or phone..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="pl-9 h-10 rounded-xl border-line bg-[#FFFDF9] focus-visible:ring-coral/30"
              data-testid="calls-search-input"
            />
          </div>
          <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1); }}>
            <SelectTrigger className="w-40 h-10 rounded-xl border-line bg-[#FFFDF9]" data-testid="status-filter-select">
              <SelectValue placeholder="Filter status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All Status</SelectItem>
              <SelectItem value="COMPLETED">Completed</SelectItem>
              <SelectItem value="ESCALATED">Escalated</SelectItem>
              <SelectItem value="FAILED">Failed</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Date Filters */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-ink-soft" />
            <span className="text-sm text-ink-soft">From:</span>
            <Input
              type="date"
              value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
              className="w-40 h-9 rounded-lg border-line bg-[#FFFDF9]"
              data-testid="date-from-input"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-ink-soft">To:</span>
            <Input
              type="date"
              value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
              className="w-40 h-9 rounded-lg border-line bg-[#FFFDF9]"
              data-testid="date-to-input"
            />
          </div>
          {(dateFrom || dateTo) && (
            <button
              onClick={clearDateFilters}
              className="text-xs font-semibold text-coral hover:text-coral-deep"
            >
              Clear dates
            </button>
          )}
        </div>
      </div>

      <div className="dash-card overflow-hidden">
        <div className="divide-y divide-line">
          {loading ? [...Array(5)].map((_, i) => <div key={i} className="p-4 h-20 animate-pulse bg-[#F6EEE4]" />) : calls.length === 0 ? (
            <div className="p-12 text-center">
              <Phone className="w-10 h-10 text-ink-soft/30 mx-auto mb-3" />
              <p className="text-sm text-ink-soft">No calls found</p>
            </div>
          ) : (
            calls.map((call, i) => {
              const StatusIcon = statusIcons[call.status] || Phone;
              const tint = statusTint[call.status] || "b-coral";
              return (
                <motion.div
                  key={call.id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.03 }}
                  onClick={() => openCallDetail(call.id)}
                  className="flex items-center gap-4 p-4 hover:bg-[#FBF4EC] cursor-pointer transition-colors"
                  data-testid={`call-row-${call.id}`}
                >
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${tint}`}>
                    <StatusIcon className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium truncate">{call.caller_name || "Unknown Caller"}</p>
                      <span className={`chip ${tint}`}>{call.status}</span>
                    </div>
                    <p className="text-xs text-ink-soft mt-0.5">{call.caller_number} · {formatTime(call.started_at)}</p>
                  </div>
                  <div className="hidden sm:flex items-center gap-4 text-right">
                    <div className="flex items-center gap-1 text-xs text-ink-soft"><Clock className="w-3 h-3" />{formatDuration(call.duration_seconds)}</div>
                    {call.quality_score ? <div className="flex items-center gap-1 text-xs"><Star className="w-3 h-3 text-[#F2A93B]" /><span className="font-medium">{call.quality_score}</span></div> : null}
                    {call.order_total > 0 ? <span className="text-sm font-medium">${(call.order_total / 100).toFixed(2)}</span> : null}
                  </div>
                </motion.div>
              );
            })
          )}
        </div>

        {pages > 1 && (
          <div className="flex items-center justify-between p-4 border-t border-line">
            <p className="text-xs text-ink-soft">Page {page} of {pages}</p>
            <div className="flex gap-1.5">
              <button className="h-9 w-9 inline-flex items-center justify-center rounded-xl border border-line bg-[#FFFDF9] hover:border-ink/25 transition disabled:opacity-40" disabled={page === 1} onClick={() => setPage(page - 1)}><ChevronLeft className="w-4 h-4" /></button>
              <button className="h-9 w-9 inline-flex items-center justify-center rounded-xl border border-line bg-[#FFFDF9] hover:border-ink/25 transition disabled:opacity-40" disabled={page === pages} onClick={() => setPage(page + 1)}><ChevronRight className="w-4 h-4" /></button>
            </div>
          </div>
        )}
      </div>

      <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
        <SheetContent className="w-full sm:max-w-lg overflow-y-auto bg-cream">
          {selectedCall && (
            <>
              <SheetHeader><SheetTitle className="font-display">{selectedCall.caller_name || "Unknown Caller"}</SheetTitle></SheetHeader>
              <div className="mt-4 space-y-5">
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-3 rounded-xl bg-[#FBF4EC]"><p className="text-xs text-ink-soft">Phone</p><p className="text-sm font-medium">{selectedCall.caller_number}</p></div>
                  <div className="p-3 rounded-xl bg-[#FBF4EC]"><p className="text-xs text-ink-soft">Duration</p><p className="text-sm font-medium">{formatDuration(selectedCall.duration_seconds)}</p></div>
                  <div className="p-3 rounded-xl bg-[#FBF4EC]"><p className="text-xs text-ink-soft">Status</p><span className={`chip mt-1 inline-block ${statusTint[selectedCall.status] || "b-coral"}`}>{selectedCall.status}</span></div>
                  <div className="p-3 rounded-xl bg-[#FBF4EC]"><p className="text-xs text-ink-soft">Quality Score</p><p className="text-sm font-medium">{selectedCall.quality_score != null ? selectedCall.quality_score : "Unavailable"}</p></div>
                </div>

                {selectedCall.order_json && (
                  <>
                    <Separator />
                    <div>
                      <h4 className="text-sm font-display font-semibold mb-3">Order Summary</h4>
                      <div className="space-y-2 rounded-xl bg-[#FBF4EC] p-3">
                        {(selectedCall.order_json.items || []).map((item: OrderItem, i: number) => (
                          <div key={i} className="flex justify-between text-sm">
                            <span>
                              {item.quantity}x {item.name}
                              {item.modifiers?.length > 0 && (
                                <span className="text-ink-soft"> ({item.modifiers.join(", ")})</span>
                              )}
                            </span>
                            <span className="text-ink-soft">${(item.subtotal / 100).toFixed(2)}</span>
                          </div>
                        ))}
                        <Separator />
                        <div className="flex justify-between text-sm font-semibold"><span>Total</span><span>${(selectedCall.order_json.total / 100).toFixed(2)}</span></div>
                        <div className="flex flex-wrap items-center gap-2 pt-1">
                          <span className="chip b-muted">{orderTypeLabel(selectedCall.order_json.order_type)}</span>
                          {selectedCall.order_json.state === "DISPATCH_FAILED" && (
                            <span
                              className="chip bg-red-500/10 text-red-600"
                              title={selectedCall.order_json.dispatch_failure_reason || "POS dispatch failed"}
                            >
                              Failed — enter manually
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </>
                )}

                {selectedCall.analysis_json && (
                  <>
                    <Separator />
                    <div>
                      <span className="ai-tag mb-3"><Sparkles className="w-3 h-3" />AI analysis</span>
                      {selectedCall.analysis_json.analysis_available === false ? (
                        <p className="text-sm text-ink-soft italic mt-3">Automated quality analysis was unavailable for this call.</p>
                      ) : (
                        <div className="mt-3">
                          <p className="text-sm text-ink-soft mb-3">{selectedCall.analysis_json.summary}</p>
                          {selectedCall.analysis_json.highlights?.length > 0 && <div className="mb-3"><p className="text-xs font-semibold text-[#2f7d5e] mb-1.5">Highlights</p><div className="flex flex-wrap gap-1.5">{selectedCall.analysis_json.highlights.map((h: string, i: number) => <span key={i} className="chip b-success">{h}</span>)}</div></div>}
                          {selectedCall.analysis_json.issues?.length > 0 && <div><p className="text-xs font-semibold text-[#a26d0d] mb-1.5">Issues</p><div className="flex flex-wrap gap-1.5">{selectedCall.analysis_json.issues.map((issue: string, i: number) => <span key={i} className="chip b-honey">{issue}</span>)}</div></div>}
                        </div>
                      )}
                    </div>
                  </>
                )}

                <Separator />
                <div>
                  <h4 className="text-sm font-display font-semibold mb-3">Transcript</h4>
                  <ScrollArea className="h-[380px] pr-3">
                    <div className="space-y-3">
                      {(selectedCall.transcript || []).map((entry: TranscriptEntry, i: number) => (
                        <div key={i} className={`flex gap-2 ${entry.role === "customer" ? "justify-end" : "justify-start"}`}>
                          {entry.role === "ai" && <div className="w-6 h-6 rounded-full bg-coral/10 flex items-center justify-center flex-shrink-0 mt-0.5"><Bot className="w-3 h-3 text-coral" /></div>}
                          <div className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${entry.role === "customer" ? "bg-coral text-white rounded-br-sm" : "bg-[#F2E8DC] text-ink rounded-bl-sm"}`}>
                            {entry.text}
                            <p className={`text-xs mt-1 ${entry.role === "customer" ? "text-white/60" : "text-ink-soft"}`}>{entry.timestamp}</p>
                          </div>
                          {entry.role === "customer" && <div className="w-6 h-6 rounded-full bg-ink/10 flex items-center justify-center flex-shrink-0 mt-0.5"><User className="w-3 h-3 text-ink" /></div>}
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
};

export default CallsPage;
