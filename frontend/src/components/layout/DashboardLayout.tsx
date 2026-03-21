import { useEffect, useState, useCallback } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { Bell, Calendar, ChevronLeft, ChevronRight, CreditCard, LayoutDashboard, LogOut, Menu, Phone, PhoneCall, Plug, Settings, ShoppingBag, UtensilsCrossed, Briefcase, X, CheckCircle2, AlertTriangle, Info, PhoneIncoming, Wifi, WifiOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { SignOutButton, UserButton } from "@clerk/clerk-react";
import { useAppSession } from "@/context/AppSessionContext";
import { getConfig } from "@/lib/api";
import { useWebSocketNotifications } from "@/hooks/useWebSocketNotifications";
import { toast } from "sonner";

// Notification types
interface Notification {
  id: string;
  type: "call" | "order" | "alert" | "info" | "appointment" | "reminder" | "system";
  title: string;
  message: string;
  time: string;
  read: boolean;
}

const notificationIcons: Record<string, any> = {
  call: PhoneIncoming,
  order: ShoppingBag,
  alert: AlertTriangle,
  info: Info,
  appointment: Calendar,
  reminder: Bell,
  system: Info,
};

const notificationColors: Record<string, string> = {
  call: "text-primary bg-primary/10",
  order: "text-success bg-success/10",
  alert: "text-warning bg-warning/10",
  info: "text-blue-500 bg-blue-500/10",
  appointment: "text-purple-500 bg-purple-500/10",
  reminder: "text-amber-500 bg-amber-500/10",
  system: "text-gray-500 bg-gray-500/10",
};

// Base nav items (always shown)
const baseNavItems = [
  { icon: LayoutDashboard, label: "Dashboard", path: "/dashboard" },
  { icon: PhoneCall, label: "Calls", path: "/dashboard/calls" },
];

// Restaurant-specific nav items
const restaurantNavItems = [
  { icon: UtensilsCrossed, label: "Menu", path: "/dashboard/menu" },
  { icon: ShoppingBag, label: "Orders", path: "/dashboard/orders" },
];

// Appointment business nav items
const appointmentNavItems = [
  { icon: Briefcase, label: "Services", path: "/dashboard/services" },
  { icon: Calendar, label: "Appointments", path: "/dashboard/appointments" },
];

// Common tail nav items
const tailNavItems = [
  { icon: Plug, label: "Integrations", path: "/dashboard/integrations" },
  { icon: CreditCard, label: "Billing", path: "/dashboard/billing" },
  { icon: Settings, label: "Settings", path: "/dashboard/settings" },
];

const DashboardLayout = () => {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [businessType, setBusinessType] = useState<string>("restaurant");
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const location = useLocation();
  const { activeRestaurant } = useAppSession();

  // WebSocket notifications with real-time updates
  const handleWebSocketNotification = useCallback((wsNotification: any) => {
    const notification: Notification = {
      id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      type: wsNotification.event as Notification["type"],
      title: wsNotification.title,
      message: wsNotification.message,
      time: "Just now",
      read: false,
    };
    
    setNotifications(prev => [notification, ...prev].slice(0, 50));
    
    // Show toast for high-priority notifications
    if (wsNotification.priority === "high") {
      toast(wsNotification.title, {
        description: wsNotification.message,
        duration: 5000,
      });
    }
  }, []);

  const { connected: wsConnected } = useWebSocketNotifications({
    restaurantId: activeRestaurant?.id,
    onNotification: handleWebSocketNotification,
    autoReconnect: true,
  });

  const unreadCount = notifications.filter(n => !n.read).length;

  const markAsRead = (id: string) => {
    setNotifications(prev => 
      prev.map(n => n.id === id ? { ...n, read: true } : n)
    );
  };

  const markAllAsRead = () => {
    setNotifications(prev => prev.map(n => ({ ...n, read: true })));
  };

  const dismissNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
  };

  // Fetch business type from config
  useEffect(() => {
    const fetchConfig = async () => {
      if (!activeRestaurant?.id) return;
      try {
        const res = await getConfig(activeRestaurant.id);
        setBusinessType(res.data?.business_type || "restaurant");
      } catch (err) {
        console.warn("Could not fetch config for business type");
      }
    };
    fetchConfig();
  }, [activeRestaurant?.id]);

  const isAppointmentBusiness = ["clinic", "salon", "home_services", "legal"].includes(businessType);

  // Build nav items based on business type
  const navItems = [
    ...baseNavItems,
    ...(isAppointmentBusiness ? appointmentNavItems : restaurantNavItems),
    ...tailNavItems,
  ];

  const isActive = (path: string) => location.pathname === path || (path !== "/dashboard" && location.pathname.startsWith(path));

  const sidebar = (
    <div className="flex flex-col h-full">
      <div className="h-16 flex items-center px-4 border-b border-border/50">
        <Link to="/dashboard" className="flex items-center gap-2.5 overflow-hidden">
          <div className="w-9 h-9 rounded-xl bg-gradient-primary flex items-center justify-center shrink-0">
            <Phone className="w-4 h-4 text-primary-foreground" />
          </div>
          {!collapsed && <span className="font-display font-bold text-lg whitespace-nowrap">Ring<span className="text-gradient">AI</span></span>}
        </Link>
      </div>

      <ScrollArea className="flex-1 py-4 px-3">
        <nav className="space-y-1">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              onClick={() => setMobileOpen(false)}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${isActive(item.path) ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:text-foreground hover:bg-muted/50"}`}
            >
              <item.icon className="w-5 h-5 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          ))}
        </nav>
      </ScrollArea>

      <Separator />
      <div className="p-3 space-y-2">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="hidden lg:flex w-full items-center justify-center gap-2 px-3 py-2 rounded-xl text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <><ChevronLeft className="w-4 h-4" /><span>Collapse</span></>}
        </button>
        <SignOutButton redirectUrl="/">
          <button className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-xl text-sm text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors">
            <LogOut className="w-4 h-4" />
            {!collapsed && <span>Sign Out</span>}
          </button>
        </SignOutButton>
      </div>
    </div>
  );

  const currentLabel = navItems.find((n) => isActive(n.path))?.label || "Dashboard";

  return (
    <div className="min-h-screen bg-background flex">
      <aside className={`${collapsed ? "w-[72px]" : "w-60"} hidden lg:flex border-r border-border/50 bg-card flex-col transition-all duration-300 shrink-0`}>
        {sidebar}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setMobileOpen(false)} />
          <aside className="relative w-64 h-full bg-card border-r border-border/50">{sidebar}</aside>
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-16 border-b border-border/50 bg-card/80 backdrop-blur-xl flex items-center justify-between px-4 lg:px-6">
          <div className="flex items-center gap-3 min-w-0">
            <Button variant="ghost" size="icon" className="rounded-xl lg:hidden" onClick={() => setMobileOpen(true)}>
              <Menu className="w-5 h-5" />
            </Button>
            <div className="min-w-0">
              <h2 className="font-display font-semibold text-lg truncate">{currentLabel}</h2>
              <p className="text-xs text-muted-foreground truncate">
                {activeRestaurant?.name || "RingAI Workspace"}
                {activeRestaurant?.cuisine_type ? ` · ${activeRestaurant.cuisine_type}` : ""}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <Badge variant="secondary" className="hidden sm:inline-flex bg-success/10 text-success border-0">
              <div className="w-1.5 h-1.5 rounded-full bg-success mr-1.5" /> AI Active
            </Badge>
            
            {/* WebSocket Status Indicator */}
            <div className="hidden sm:flex items-center gap-1" title={wsConnected ? "Real-time updates connected" : "Connecting to real-time updates..."}>
              {wsConnected ? (
                <Wifi className="w-4 h-4 text-success" />
              ) : (
                <WifiOff className="w-4 h-4 text-muted-foreground animate-pulse" />
              )}
            </div>
            
            {/* Notifications Popover */}
            <Popover open={notificationsOpen} onOpenChange={setNotificationsOpen}>
              <PopoverTrigger asChild>
                <Button 
                  variant="ghost" 
                  size="icon" 
                  className="rounded-xl relative"
                  data-testid="notifications-btn"
                >
                  <Bell className="w-5 h-5" />
                  {unreadCount > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 w-5 h-5 rounded-full bg-destructive text-destructive-foreground text-xs flex items-center justify-center font-medium">
                      {unreadCount}
                    </span>
                  )}
                </Button>
              </PopoverTrigger>
              <PopoverContent 
                align="end" 
                className="w-80 p-0"
                data-testid="notifications-panel"
              >
                <div className="flex items-center justify-between p-4 border-b">
                  <div className="flex items-center gap-2">
                    <h4 className="font-display font-semibold">Notifications</h4>
                    {wsConnected && (
                      <span className="flex items-center gap-1 text-xs text-success">
                        <div className="w-1.5 h-1.5 rounded-full bg-success" />
                        Live
                      </span>
                    )}
                  </div>
                  {unreadCount > 0 && (
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      className="text-xs h-auto py-1"
                      onClick={markAllAsRead}
                    >
                      Mark all read
                    </Button>
                  )}
                </div>
                <ScrollArea className="max-h-[400px]">
                  {notifications.length === 0 ? (
                    <div className="p-8 text-center">
                      <Bell className="w-8 h-8 text-muted-foreground/30 mx-auto mb-2" />
                      <p className="text-sm text-muted-foreground">No notifications</p>
                    </div>
                  ) : (
                    <div className="divide-y">
                      {notifications.map((notification) => {
                        const Icon = notificationIcons[notification.type] || Info;
                        const colorClass = notificationColors[notification.type] || notificationColors.info;
                        return (
                          <div 
                            key={notification.id}
                            className={`p-4 hover:bg-muted/50 transition-colors cursor-pointer ${!notification.read ? "bg-primary/5" : ""}`}
                            onClick={() => markAsRead(notification.id)}
                            data-testid={`notification-${notification.id}`}
                          >
                            <div className="flex gap-3">
                              <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${colorClass}`}>
                                <Icon className="w-4 h-4" />
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-start justify-between gap-2">
                                  <p className={`text-sm font-medium ${!notification.read ? "text-foreground" : "text-muted-foreground"}`}>
                                    {notification.title}
                                  </p>
                                  <button 
                                    onClick={(e) => { e.stopPropagation(); dismissNotification(notification.id); }}
                                    className="text-muted-foreground hover:text-foreground"
                                  >
                                    <X className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                                <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                                  {notification.message}
                                </p>
                                <p className="text-xs text-muted-foreground/70 mt-1">
                                  {notification.time}
                                </p>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </ScrollArea>
                <div className="p-2 border-t">
                  <Button variant="ghost" className="w-full text-xs" size="sm">
                    View all notifications
                  </Button>
                </div>
              </PopoverContent>
            </Popover>
            
            <UserButton afterSignOutUrl="/" />
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;
