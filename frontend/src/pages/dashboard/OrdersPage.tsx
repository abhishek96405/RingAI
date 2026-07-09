import { useCallback, useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { getCalls, getRestaurantId, refundOrder } from "@/lib/api";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { getApiErrorMessage } from "@/lib/errors";
import type { Call, OrderItem } from "@/types";
import {
  Search,
  ShoppingBag,
  Phone,
  User,
  Clock,
  DollarSign,
  ChevronLeft,
  ChevronRight,
  Receipt,
  AlertTriangle,
} from "lucide-react";

// Pretty label for an order's fulfillment type. Food orders are "pickup"/"delivery";
// a "+reservation" suffix marks a dual-intent call (food order placed alongside a table
// reservation). Unknown/missing falls back to "Pickup" to preserve prior behavior.
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

// Compact base label for the narrow list column; the "+ Reservation" part is rendered
// on a separate sub-line so it can never overflow the column.
const orderBaseLabel = (t?: string): string =>
  t?.startsWith("delivery") ? "Delivery" : t === "reservation" ? "Reservation" : "Pickup";

const OrdersPage = () => {
  const [orders, setOrders] = useState<Call[]>([]);
  const [filtered, setFiltered] = useState<Call[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [failedOnly, setFailedOnly] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState<Call | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [refunding, setRefunding] = useState(false);

  const PAGE_SIZE = 15;

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const restaurantId = getRestaurantId();
      if (!restaurantId) { setOrders([]); setFiltered([]); return; }

      // Load ALL order-bearing calls (orders live on COMPLETED or ESCALATED calls),
      // not just the first few pages — otherwise older orders silently vanish (C9-3).
      // Page 1 reports the page count; the rest are fetched in parallel. MAX_PAGES is
      // a stopgap safety cap (50 × 100 = 5k calls/status) until the dedicated
      // server-side /orders endpoint replaces this client-side load.
      const MAX_PAGES = 50;
      const fetchAllCalls = async (status: string) => {
        const first = await getCalls(restaurantId, { page: 1, limit: 100, status });
        const calls = [...(first.data.calls || [])];
        const pages = Math.min(first.data.pages || 1, MAX_PAGES);
        if (pages > 1) {
          const rest = await Promise.all(
            Array.from({ length: pages - 1 }, (_, i) =>
              getCalls(restaurantId, { page: i + 2, limit: 100, status })
            )
          );
          rest.forEach((r) => calls.push(...(r.data.calls || [])));
        }
        return calls;
      };
      const [completedCalls, escalatedCalls] = await Promise.all([
        fetchAllCalls("COMPLETED"),
        fetchAllCalls("ESCALATED"),
      ]);
      const allCalls = [...completedCalls, ...escalatedCalls];

      const withOrders = allCalls.filter(
        (c: Call) => c.order_json && c.order_json.items && c.order_json.items.length > 0
      );
      setOrders(withOrders);
      setFiltered(withOrders);
    } catch (err) {
      console.error(err);
      toast.error("Failed to load orders");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

  // Search + "failed only" filter
  useEffect(() => {
    let base = orders;
    if (failedOnly) {
      base = base.filter((o) => o.order_json?.state === "DISPATCH_FAILED");
    }
    const q = search.trim().toLowerCase();
    if (q) {
      base = base.filter(
        (o) =>
          o.caller_number?.includes(q) ||
          o.order_json?.customer_name?.toLowerCase().includes(q) ||
          o.call_sid?.toLowerCase().includes(q) ||
          o.order_json?.items?.some((i) => i.name?.toLowerCase().includes(q))
      );
    }
    setFiltered(base);
    setPage(1);
  }, [search, orders, failedOnly]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const formatDate = (iso?: string) => {
    if (!iso) return "--";
    return new Date(iso).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  };

  const formatPhone = (phone?: string) => {
    if (!phone) return "--";
    const digits = phone.replace(/\D/g, "");
    if (digits.length === 11 && digits.startsWith("1")) {
      return `+1 (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
    }
    return phone;
  };

  const getOrderNumber = (call: Call) => {
    const sid = call.call_sid || call.id || "";
    return `DTH-${sid.slice(-8).toUpperCase()}`;
  };

  // A DISPATCH_FAILED order was confirmed with the caller but never reached the POS
  // (or its delivery address couldn't be verified) — money not actually earned, so
  // it's excluded from revenue and the average. It still counts as an order the AI
  // captured, so Total Orders stays orders.length.
  const fulfilledOrders = orders.filter(
    (o) => o.order_json?.state !== "DISPATCH_FAILED"
  );
  const totalRevenue = fulfilledOrders.reduce((sum, o) => sum + (o.order_total || 0), 0);
  const avgOrder = fulfilledOrders.length > 0 ? totalRevenue / fulfilledOrders.length : 0;
  const failedCount = orders.length - fulfilledOrders.length;

  const handleRefund = async () => {
    if (!selectedOrder) return;
    const callSid = selectedOrder.call_sid;
    const amount = ((selectedOrder.order_total || 0) / 100).toFixed(2);
    if (!window.confirm(`Refund $${amount} to the customer? This cannot be undone.`)) return;
    setRefunding(true);
    try {
      const restaurantId = getRestaurantId();
      if (!restaurantId) throw new Error("No restaurant selected");
      await refundOrder(restaurantId, callSid);
      toast.success("Order refunded successfully");
      setSelectedOrder({ ...selectedOrder, payment_status: "refunded" });
      setOrders((prev) =>
        prev.map((o) =>
          o.call_sid === callSid ? { ...o, payment_status: "refunded" } : o
        )
      );
      setFiltered((prev) =>
        prev.map((o) =>
          o.call_sid === callSid ? { ...o, payment_status: "refunded" } : o
        )
      );
    } catch (err) {
      const msg = getApiErrorMessage(err, "Refund failed");
      toast.error(msg);
    } finally {
      setRefunding(false);
    }
  };

  if (loading) {
    return (
      <div className="dash space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="dash-card h-24 animate-pulse" />
          ))}
        </div>
        <div className="dash-card h-96 animate-pulse" />
      </div>
    );
  }

  return (
    <div className="dash space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <p className="eyebrow mb-2">Orders</p>
          <h1 className="text-2xl font-display font-bold">Order History</h1>
          <p className="text-sm text-ink-soft mt-1">
            All orders placed through your AI phone agent
          </p>
        </div>
        <button
          onClick={fetchOrders}
          className="border border-line bg-[#FFFDF9] hover:border-ink/25 px-4 py-2 rounded-xl text-sm font-semibold transition"
        >
          Refresh
        </button>
      </div>

      {/* Dispatch-failure banner — orders that need manual entry (C9-1) */}
      {failedCount > 0 && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-red-600">
              {failedCount} order{failedCount > 1 ? "s" : ""} need manual entry
            </p>
            <p className="text-xs text-red-600/80 mt-0.5">
              These were confirmed with the caller but couldn't be sent to your POS,
              or the delivery address couldn't be verified. Open each one (look for the
              red "Failed — enter manually" tag) and enter it into your system so it
              isn't missed.
            </p>
          </div>
          <button
            className="shrink-0 border border-red-300 text-red-600 hover:bg-red-50 px-3 py-1.5 rounded-lg text-sm font-semibold transition"
            onClick={() => setFailedOnly((v) => !v)}
          >
            {failedOnly ? "Show all" : "Show failed"}
          </button>
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="dash-card card-hover p-5">
          <span className="h-10 w-10 rounded-2xl flex items-center justify-center text-white bg-gradient-to-br from-[#F2946E] to-[#E87A5E] icon-tile">
            <ShoppingBag className="w-[18px] h-[18px]" />
          </span>
          <p className="font-display font-extrabold text-3xl mt-4">{orders.length}</p>
          <p className="text-sm text-ink-soft">Total Orders</p>
        </div>
        <div className="dash-card card-hover p-5">
          <span className="h-10 w-10 rounded-2xl flex items-center justify-center text-white bg-gradient-to-br from-[#4FB089] to-[#3E9E78]" style={{ boxShadow: "0 10px 20px -8px rgba(62,158,120,.5)" }}>
            <DollarSign className="w-[18px] h-[18px]" />
          </span>
          <p className="font-display font-extrabold text-3xl mt-4">${(totalRevenue / 100).toFixed(2)}</p>
          <p className="text-sm text-ink-soft">Total Revenue</p>
        </div>
        <div className="dash-card card-hover p-5">
          <span className="h-10 w-10 rounded-2xl flex items-center justify-center text-white bg-gradient-to-br from-[#F6BE5C] to-[#F2A93B]" style={{ boxShadow: "0 10px 20px -8px rgba(242,169,59,.5)" }}>
            <Receipt className="w-[18px] h-[18px]" />
          </span>
          <p className="font-display font-extrabold text-3xl mt-4">${(avgOrder / 100).toFixed(2)}</p>
          <p className="text-sm text-ink-soft">Average Order Value</p>
        </div>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-soft" />
        <Input
          className="pl-9 h-10 rounded-xl border-line bg-[#FFFDF9] focus-visible:ring-coral/30"
          placeholder="Search by name, phone, order number, or item..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Orders table */}
      <div className="dash-card p-0 overflow-hidden">
        {/* Table header */}
        <div className="grid grid-cols-12 gap-4 px-5 py-3 bg-[#FBF4EC] border-b border-line text-xs font-semibold text-ink-soft">
          <div className="col-span-2">Order #</div>
          <div className="col-span-2">Customer</div>
          <div className="col-span-2">Phone</div>
          <div className="col-span-2">Items</div>
          <div className="col-span-1">Type</div>
          <div className="col-span-1">Total</div>
          <div className="col-span-2">Date</div>
        </div>

        {paginated.length === 0 ? (
          <div className="py-16 text-center">
            <ShoppingBag className="w-10 h-10 text-ink-soft/30 mx-auto mb-3" />
            <p className="text-sm text-ink-soft">No orders found</p>
          </div>
        ) : (
          <div className="divide-y divide-line">
            {paginated.map((order, i) => {
              const items = order.order_json?.items || [];
              const name = order.order_json?.customer_name || "Unknown";
              const itemSummary = items
                .slice(0, 2)
                .map((it) => `${it.quantity}x ${it.name}`)
                .join(", ");
              const extra = items.length > 2 ? ` +${items.length - 2} more` : "";
              const isDelivery = order.order_json?.order_type?.startsWith("delivery");

              return (
                <motion.div
                  key={order.id || i}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03 }}
                  className="grid grid-cols-12 gap-4 px-5 py-4 items-center hover:bg-[#FBF4EC] transition-colors cursor-pointer text-sm"
                  onClick={() => {
                    setSelectedOrder(order);
                    setDrawerOpen(true);
                  }}
                >
                  <div className="col-span-2">
                    <span className="chip b-coral font-mono">{getOrderNumber(order)}</span>
                    {order.order_json?.state === "DISPATCH_FAILED" && (
                      <span
                        className="chip bg-red-500/10 text-red-600 text-[10px] mt-1 block w-fit"
                        title={order.order_json?.dispatch_failure_reason || "POS dispatch failed"}
                      >
                        Failed — enter manually
                      </span>
                    )}
                  </div>
                  <div className="col-span-2 flex items-center gap-1.5 min-w-0">
                    <User className="w-3.5 h-3.5 text-ink-soft shrink-0" />
                    <span className="truncate font-medium">{name}</span>
                  </div>
                  <div className="col-span-2 flex items-center gap-1.5 text-ink-soft">
                    <Phone className="w-3.5 h-3.5 shrink-0" />
                    <span className="text-xs">{formatPhone(order.caller_number)}</span>
                  </div>
                  <div className="col-span-2 text-ink-soft truncate text-xs">
                    {itemSummary}
                    {extra && (
                      <span className="text-coral font-medium">{extra}</span>
                    )}
                  </div>
                  <div className="col-span-1 flex flex-col items-start gap-0.5">
                    <span className={`chip ${isDelivery ? "bg-blue-500/10 text-blue-600" : "b-success"}`}>
                      {orderBaseLabel(order.order_json?.order_type)}
                    </span>
                    {order.order_json?.order_type?.includes("reservation") &&
                      order.order_json?.order_type !== "reservation" && (
                        <span className="text-[10px] leading-tight text-coral font-medium">
                          + Reservation
                        </span>
                      )}
                  </div>
                  <div className="col-span-1 font-semibold text-[#2f7d5e]">
                    ${((order.order_total || 0) / 100).toFixed(2)}
                  </div>
                  <div className="col-span-2 text-xs text-ink-soft whitespace-nowrap">
                    {formatDate(order.started_at)}
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <p className="text-ink-soft">
            Showing {(page - 1) * PAGE_SIZE + 1}–
            {Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}
          </p>
          <div className="flex items-center gap-2">
            <button
              className="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-line bg-[#FFFDF9] hover:border-ink/25 transition disabled:opacity-40"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-ink-soft">
              {page} / {totalPages}
            </span>
            <button
              className="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-line bg-[#FFFDF9] hover:border-ink/25 transition disabled:opacity-40"
              disabled={page === totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Order detail drawer */}
      <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
        <SheetContent className="w-full sm:max-w-md overflow-y-auto bg-cream">
          {selectedOrder && (
            <>
              <SheetHeader className="mb-6">
                <SheetTitle className="font-display">
                  {getOrderNumber(selectedOrder)}
                </SheetTitle>
                <p className="text-sm text-ink-soft">
                  {formatDate(selectedOrder.started_at)}
                </p>
              </SheetHeader>

              <div className="space-y-5">
                {/* Customer info */}
                <div className="dash-card p-4 space-y-3">
                  <p className="text-xs font-semibold text-ink-soft uppercase tracking-wider">
                    Customer
                  </p>
                  <div className="flex items-center gap-2">
                    <User className="w-4 h-4 text-ink-soft" />
                    <span className="text-sm font-medium">
                      {selectedOrder.order_json?.customer_name || "Unknown"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Phone className="w-4 h-4 text-ink-soft" />
                    <span className="text-sm">
                      {formatPhone(selectedOrder.caller_number)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-ink-soft" />
                    <span className="text-sm">
                      {orderTypeLabel(selectedOrder.order_json?.order_type)}
                    </span>
                  </div>
                  {selectedOrder.order_json?.delivery_address && (
                    <p className="text-sm text-ink-soft pl-6">
                      {selectedOrder.order_json.delivery_address}
                    </p>
                  )}
                </div>

                {/* Items */}
                <div className="dash-card p-4 space-y-3">
                  <p className="text-xs font-semibold text-ink-soft uppercase tracking-wider">
                    Items Ordered
                  </p>
                  <div className="space-y-2">
                    {(selectedOrder.order_json?.items || []).map(
                      (item: OrderItem, i: number) => (
                        <div
                          key={i}
                          className="flex items-start justify-between gap-2"
                        >
                          <div className="flex items-start gap-2 min-w-0">
                            <span className="text-sm font-medium text-ink-soft shrink-0">
                              {item.quantity}×
                            </span>
                            <div className="min-w-0">
                              <p className="text-sm font-medium">{item.name}</p>
                              {item.modifiers?.length > 0 && (
                                <p className="text-xs text-ink-soft">
                                  {item.modifiers.join(", ")}
                                </p>
                              )}
                              {item.special_instructions && (
                                <p className="text-xs text-ink-soft italic">
                                  {item.special_instructions}
                                </p>
                              )}
                            </div>
                          </div>
                          {item.unit_price > 0 && (
                            <span className="text-sm shrink-0">
                              ${(item.subtotal / 100).toFixed(2)}
                            </span>
                          )}
                        </div>
                      )
                    )}
                  </div>

                  <div className="border-t border-line pt-3 flex items-center justify-between">
                    <span className="text-sm font-semibold">Total</span>
                    <span className="text-lg font-display font-bold text-[#2f7d5e]">
                      ${((selectedOrder.order_total || 0) / 100).toFixed(2)}
                    </span>
                  </div>
                </div>

                {/* Special instructions */}
                {selectedOrder.order_json?.special_instructions && (
                  <div className="dash-card p-4 space-y-2">
                    <p className="text-xs font-semibold text-ink-soft uppercase tracking-wider">
                      Special Instructions
                    </p>
                    <p className="text-sm">
                      {selectedOrder.order_json.special_instructions}
                    </p>
                  </div>
                )}

                {/* Order meta */}
                <div className="dash-card p-4 space-y-2">
                  <p className="text-xs font-semibold text-ink-soft uppercase tracking-wider">
                    Order Details
                  </p>
                  <div className="space-y-1.5 text-sm">
                    <div className="flex justify-between">
                      <span className="text-ink-soft">Order #</span>
                      <span className="font-mono text-xs">
                        {getOrderNumber(selectedOrder)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-ink-soft">Call SID</span>
                      <span className="font-mono text-xs truncate max-w-[180px]">
                        {selectedOrder.call_sid}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-ink-soft">Status</span>
                      <span className="chip b-success">{selectedOrder.status}</span>
                    </div>
                    {selectedOrder.order_json?.state === "DISPATCH_FAILED" && (
                      <div className="flex justify-between items-center">
                        <span className="text-ink-soft">Dispatch</span>
                        <span
                          className="chip bg-red-500/10 text-red-600"
                          title={selectedOrder.order_json?.dispatch_failure_reason || "POS dispatch failed"}
                        >
                          Failed — enter manually
                        </span>
                      </div>
                    )}
                    {selectedOrder.payment_status && (
                      <div className="flex justify-between items-center">
                        <span className="text-ink-soft">Payment</span>
                        <span
                          className={`chip ${
                            selectedOrder.payment_status === "paid"
                              ? "b-success"
                              : selectedOrder.payment_status === "refunded"
                              ? "bg-orange-500/10 text-orange-600"
                              : "b-muted"
                          }`}
                        >
                          {selectedOrder.payment_status === "paid"
                            ? "Paid"
                            : selectedOrder.payment_status === "refunded"
                            ? "Refunded"
                            : selectedOrder.payment_status}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Refund action */}
                {selectedOrder.payment_status === "paid" && (
                  <button
                    className="w-full rounded-xl border border-red-300 text-red-600 hover:bg-red-50 px-4 py-2.5 text-sm font-semibold transition disabled:opacity-50"
                    onClick={handleRefund}
                    disabled={refunding}
                  >
                    {refunding ? "Processing Refund..." : "Refund Order"}
                  </button>
                )}
                {selectedOrder.payment_status === "refunded" && (
                  <div className="text-center text-sm text-ink-soft py-2">
                    This order has been refunded
                  </div>
                )}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
};

export default OrdersPage;
