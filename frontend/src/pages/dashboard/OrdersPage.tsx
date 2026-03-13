import { useCallback, useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { getCalls, getRestaurantId } from "@/lib/api";
import { motion } from "framer-motion";
import { toast } from "sonner";
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
} from "lucide-react";

const OrdersPage = () => {
  const [orders, setOrders] = useState<any[]>([]);
  const [filtered, setFiltered] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selectedOrder, setSelectedOrder] = useState<any>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const PAGE_SIZE = 15;

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const restaurantId = getRestaurantId();
      if (!restaurantId) { setOrders([]); setFiltered([]); return; }

    // Fetch up to 3 pages to get up to 300 orders
      const res1 = await getCalls(restaurantId, { page: 1, limit: 100, status: "COMPLETED" });
      const data = res1.data;
      let allCalls = data.calls || [];

      if (data.pages > 1) {
        const res2 = await getCalls(restaurantId, { page: 2, limit: 100, status: "COMPLETED" });
        allCalls = [...allCalls, ...(res2.data.calls || [])];
      }
      if (data.pages > 2) {
        const res3 = await getCalls(restaurantId, { page: 3, limit: 100, status: "COMPLETED" });
        allCalls = [...allCalls, ...(res3.data.calls || [])];
      }

      const withOrders = allCalls.filter(
        (c: any) => c.order_json && c.order_json.items && c.order_json.items.length > 0
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

  // Search filter
  useEffect(() => {
    if (!search.trim()) {
      setFiltered(orders);
      setPage(1);
      return;
    }
    const q = search.toLowerCase();
    setFiltered(
      orders.filter(
        (o) =>
          o.caller_number?.includes(q) ||
          o.order_json?.customer_name?.toLowerCase().includes(q) ||
          o.twilio_call_sid?.toLowerCase().includes(q) ||
          o.order_json?.items?.some((i: any) => i.name?.toLowerCase().includes(q))
      )
    );
    setPage(1);
  }, [search, orders]);

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

  const getOrderNumber = (call: any) => {
    const sid = call.twilio_call_sid || call.id || "";
    return `RNG-${sid.slice(-8).toUpperCase()}`;
  };

  const totalRevenue = orders.reduce((sum, o) => sum + (o.order_total || 0), 0);
  const avgOrder = orders.length > 0 ? totalRevenue / orders.length : 0;

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="premium-card h-24 animate-pulse" />
          ))}
        </div>
        <div className="premium-card h-96 animate-pulse" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-display font-bold">Order History</h1>
          <p className="text-sm text-muted-foreground">
            All orders placed through your AI phone agent
          </p>
        </div>
        <Button
          variant="outline"
          className="rounded-xl"
          onClick={fetchOrders}
        >
          Refresh
        </Button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="kpi-card">
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center">
            <ShoppingBag className="w-5 h-5 text-primary" />
          </div>
          <div className="mt-3">
            <p className="text-2xl font-display font-bold">{orders.length}</p>
            <p className="text-xs text-muted-foreground">Total Orders</p>
          </div>
        </Card>
        <Card className="kpi-card">
          <div className="w-10 h-10 rounded-xl bg-success/10 flex items-center justify-center">
            <DollarSign className="w-5 h-5 text-success" />
          </div>
          <div className="mt-3">
            <p className="text-2xl font-display font-bold">
              ${(totalRevenue / 100).toFixed(2)}
            </p>
            <p className="text-xs text-muted-foreground">Total Revenue</p>
          </div>
        </Card>
        <Card className="kpi-card">
          <div className="w-10 h-10 rounded-xl bg-warning/10 flex items-center justify-center">
            <Receipt className="w-5 h-5 text-warning" />
          </div>
          <div className="mt-3">
            <p className="text-2xl font-display font-bold">
              ${(avgOrder / 100).toFixed(2)}
            </p>
            <p className="text-xs text-muted-foreground">Average Order Value</p>
          </div>
        </Card>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <Input
          className="pl-9 h-10 rounded-xl"
          placeholder="Search by name, phone, order number, or item..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Orders table */}
      <div className="premium-card p-0 overflow-hidden">
        {/* Table header */}
        <div className="grid grid-cols-12 gap-4 px-5 py-3 bg-muted/30 border-b border-border/50 text-xs font-medium text-muted-foreground">
          <div className="col-span-2">Order #</div>
          <div className="col-span-2">Customer</div>
          <div className="col-span-2">Phone</div>
          <div className="col-span-3">Items</div>
          <div className="col-span-2">Total</div>
          <div className="col-span-1">Date</div>
        </div>

        {paginated.length === 0 ? (
          <div className="py-16 text-center">
            <ShoppingBag className="w-10 h-10 text-muted-foreground/30 mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">No orders found</p>
          </div>
        ) : (
          <div className="divide-y divide-border/50">
            {paginated.map((order, i) => {
              const items = order.order_json?.items || [];
              const name = order.order_json?.customer_name || "Unknown";
              const itemSummary = items
                .slice(0, 2)
                .map((it: any) => `${it.quantity}x ${it.name}`)
                .join(", ");
              const extra = items.length > 2 ? ` +${items.length - 2} more` : "";

              return (
                <motion.div
                  key={order.id || i}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03 }}
                  className="grid grid-cols-12 gap-4 px-5 py-4 items-center hover:bg-muted/20 transition-colors cursor-pointer text-sm"
                  onClick={() => {
                    setSelectedOrder(order);
                    setDrawerOpen(true);
                  }}
                >
                  <div className="col-span-2">
                    <Badge
                      variant="secondary"
                      className="border-0 bg-primary/10 text-primary font-mono text-xs"
                    >
                      {getOrderNumber(order)}
                    </Badge>
                  </div>
                  <div className="col-span-2 flex items-center gap-1.5 min-w-0">
                    <User className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                    <span className="truncate font-medium">{name}</span>
                  </div>
                  <div className="col-span-2 flex items-center gap-1.5 text-muted-foreground">
                    <Phone className="w-3.5 h-3.5 shrink-0" />
                    <span className="text-xs">{formatPhone(order.caller_number)}</span>
                  </div>
                  <div className="col-span-3 text-muted-foreground truncate text-xs">
                    {itemSummary}
                    {extra && (
                      <span className="text-primary font-medium">{extra}</span>
                    )}
                  </div>
                  <div className="col-span-2 font-semibold text-success">
                    ${((order.order_total || 0) / 100).toFixed(2)}
                  </div>
                  <div className="col-span-1 text-xs text-muted-foreground whitespace-nowrap">
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
          <p className="text-muted-foreground">
            Showing {(page - 1) * PAGE_SIZE + 1}–
            {Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8 rounded-lg"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span className="text-muted-foreground">
              {page} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="icon"
              className="h-8 w-8 rounded-lg"
              disabled={page === totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Order detail drawer */}
      <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
        <SheetContent className="w-full sm:max-w-md overflow-y-auto">
          {selectedOrder && (
            <>
              <SheetHeader className="mb-6">
                <SheetTitle className="font-display">
                  {getOrderNumber(selectedOrder)}
                </SheetTitle>
                <p className="text-sm text-muted-foreground">
                  {formatDate(selectedOrder.started_at)}
                </p>
              </SheetHeader>

              <div className="space-y-5">
                {/* Customer info */}
                <div className="premium-card p-4 space-y-3">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Customer
                  </p>
                  <div className="flex items-center gap-2">
                    <User className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm font-medium">
                      {selectedOrder.order_json?.customer_name || "Unknown"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Phone className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm">
                      {formatPhone(selectedOrder.caller_number)}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-muted-foreground" />
                    <span className="text-sm">
                      {selectedOrder.order_json?.order_type === "delivery"
                        ? "Delivery"
                        : "Pickup"}
                    </span>
                  </div>
                  {selectedOrder.order_json?.delivery_address && (
                    <p className="text-sm text-muted-foreground pl-6">
                      {selectedOrder.order_json.delivery_address}
                    </p>
                  )}
                </div>

                {/* Items */}
                <div className="premium-card p-4 space-y-3">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Items Ordered
                  </p>
                  <div className="space-y-2">
                    {(selectedOrder.order_json?.items || []).map(
                      (item: any, i: number) => (
                        <div
                          key={i}
                          className="flex items-start justify-between gap-2"
                        >
                          <div className="flex items-start gap-2 min-w-0">
                            <span className="text-sm font-medium text-muted-foreground shrink-0">
                              {item.quantity}×
                            </span>
                            <div className="min-w-0">
                              <p className="text-sm font-medium">{item.name}</p>
                              {item.modifiers?.length > 0 && (
                                <p className="text-xs text-muted-foreground">
                                  {item.modifiers.join(", ")}
                                </p>
                              )}
                              {item.special_instructions && (
                                <p className="text-xs text-muted-foreground italic">
                                  {item.special_instructions}
                                </p>
                              )}
                            </div>
                          </div>
                          {item.unit_price > 0 && (
                            <span className="text-sm shrink-0">
                              ${((item.unit_price * item.quantity) / 100).toFixed(2)}
                            </span>
                          )}
                        </div>
                      )
                    )}
                  </div>

                  <div className="border-t border-border/50 pt-3 flex items-center justify-between">
                    <span className="text-sm font-semibold">Total</span>
                    <span className="text-lg font-display font-bold text-success">
                      ${((selectedOrder.order_total || 0) / 100).toFixed(2)}
                    </span>
                  </div>
                </div>

                {/* Special instructions */}
                {selectedOrder.order_json?.special_instructions && (
                  <div className="premium-card p-4 space-y-2">
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                      Special Instructions
                    </p>
                    <p className="text-sm">
                      {selectedOrder.order_json.special_instructions}
                    </p>
                  </div>
                )}

                {/* Order meta */}
                <div className="premium-card p-4 space-y-2">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                    Order Details
                  </p>
                  <div className="space-y-1.5 text-sm">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Order #</span>
                      <span className="font-mono text-xs">
                        {getOrderNumber(selectedOrder)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Call SID</span>
                      <span className="font-mono text-xs truncate max-w-[180px]">
                        {selectedOrder.twilio_call_sid}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Status</span>
                      <Badge
                        variant="secondary"
                        className="border-0 bg-success/10 text-success text-xs"
                      >
                        {selectedOrder.status}
                      </Badge>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
};

export default OrdersPage;
